import sqlite3
import random
from datetime import datetime, timedelta
from faker import Faker

DB_PATH = "magasin_mock.db"
NB_CLIENTS = 80
NB_FACTURES = 500

fake = Faker(["fr_FR"])
random.seed(42)
Faker.seed(42)


def random_date_last_18_months():
    now = datetime.now()
    start = now - timedelta(days=540)
    d = start + timedelta(days=random.randint(0, (now - start).days))
    return d.strftime("%Y-%m-%d")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.executescript(
        """
    DROP TABLE IF EXISTS ventes;
    DROP TABLE IF EXISTS factures;
    DROP TABLE IF EXISTS stocks;
    DROP TABLE IF EXISTS articles;
    DROP TABLE IF EXISTS clients;
    """
    )

    cur.executescript(
        """
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        ville TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        designation TEXT NOT NULL UNIQUE,
        prix_unitaire REAL NOT NULL CHECK (prix_unitaire >= 0)
    );

    CREATE TABLE IF NOT EXISTS stocks (
        id_article INTEGER PRIMARY KEY,
        quantite INTEGER NOT NULL CHECK (quantite >= 0),
        FOREIGN KEY(id_article) REFERENCES articles(id)
    );

    CREATE TABLE IF NOT EXISTS factures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_client INTEGER NOT NULL,
        date_facture TEXT NOT NULL,
        FOREIGN KEY(id_client) REFERENCES clients(id)
    );

    CREATE TABLE IF NOT EXISTS ventes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_facture INTEGER NOT NULL,
        id_article INTEGER NOT NULL,
        quantite INTEGER NOT NULL CHECK (quantite > 0),
        prix_vente_unitaire REAL NOT NULL CHECK (prix_vente_unitaire >= 0),
        FOREIGN KEY(id_facture) REFERENCES factures(id),
        FOREIGN KEY(id_article) REFERENCES articles(id)
    );

    CREATE INDEX IF NOT EXISTS idx_factures_date ON factures(date_facture);
    CREATE INDEX IF NOT EXISTS idx_factures_client ON factures(id_client);
    CREATE INDEX IF NOT EXISTS idx_ventes_facture ON ventes(id_facture);
    CREATE INDEX IF NOT EXISTS idx_ventes_article ON ventes(id_article);
    """
    )

    clients = [(fake.name(), fake.unique.email(), fake.city()) for _ in range(NB_CLIENTS)]
    cur.executemany("INSERT INTO clients (nom, email, ville) VALUES (?, ?, ?)", clients)

    produits = [
        "Ordinateur",
        "Clavier",
        "Souris",
        "Ecran",
        "Casque",
        "Imprimante",
        "Webcam",
        "Routeur",
    ]
    article_prices = {}

    for p in produits:
        prix = round(random.uniform(15.0, 1500.0), 2)
        cur.execute("INSERT INTO articles (designation, prix_unitaire) VALUES (?, ?)", (p, prix))
        article_id = cur.lastrowid
        article_prices[article_id] = prix
        cur.execute(
            "INSERT INTO stocks (id_article, quantite) VALUES (?, ?)",
            (article_id, random.randint(20, 300)),
        )

    for _ in range(NB_FACTURES):
        id_client = random.randint(1, NB_CLIENTS)
        date_facture = random_date_last_18_months()

        cur.execute(
            "INSERT INTO factures (id_client, date_facture) VALUES (?, ?)",
            (id_client, date_facture),
        )
        facture_id = cur.lastrowid

        nb_lignes = random.randint(1, 6)
        for _ in range(nb_lignes):
            id_article = random.randint(1, len(produits))
            qte = random.randint(1, 5)

            base = article_prices[id_article]
            pv = round(max(1.0, base * random.uniform(0.9, 1.1)), 2)

            cur.execute(
                """
                INSERT INTO ventes (id_facture, id_article, quantite, prix_vente_unitaire)
                VALUES (?, ?, ?, ?)
                """,
                (facture_id, id_article, qte, pv),
            )

            cur.execute("SELECT quantite FROM stocks WHERE id_article = ?", (id_article,))
            stock_now = cur.fetchone()[0]
            new_stock = max(0, stock_now - qte)
            cur.execute("UPDATE stocks SET quantite = ? WHERE id_article = ?", (new_stock, id_article))

    conn.commit()
    conn.close()
    print(f"Base '{DB_PATH}' generee avec succes.")


if __name__ == "__main__":
    main()
