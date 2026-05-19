const CHART_OPTIONS = [
  { id: 'bar', label: 'Barres' },
  { id: 'line', label: 'Courbe' },
  { id: 'pie', label: 'Secteurs' },
]

const DISPLAY_OPTIONS = [
  { id: 'auto', label: 'Auto' },
  { id: 'table', label: 'Tableau' },
  { id: 'chart', label: 'Graphique' },
]

export function PreferencesBar({ preferences, plannerReady, onPreferenceChange }) {
  return (
    <div className="preferences-bar">
      <div className="pref-group">
        <span className="pref-label">Affichage</span>
        <div className="segmented" role="group" aria-label="Mode d'affichage des réponses">
          {DISPLAY_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={preferences.displayFormat === opt.id ? 'segment active' : 'segment'}
              onClick={() => onPreferenceChange('displayFormat', opt.id)}
              aria-pressed={preferences.displayFormat === opt.id}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <span className="pref-hint">Ou écrivez « en tableau » / « en graphique »</span>
      </div>

      <div className="pref-group">
        <span className="pref-label">Graphique</span>
        <div className="segmented" role="group" aria-label="Type de graphique">
          {CHART_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={preferences.chartType === opt.id ? 'segment active' : 'segment'}
              onClick={() => onPreferenceChange('chartType', opt.id)}
              aria-pressed={preferences.chartType === opt.id}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="pref-group">
        <span className="pref-label">Planificateur</span>
        <div className="segmented" role="group" aria-label="Mode planificateur">
          <button
            type="button"
            className={!preferences.useRealPlanner ? 'segment active' : 'segment'}
            onClick={() => onPreferenceChange('useRealPlanner', false)}
            aria-pressed={!preferences.useRealPlanner}
          >
            Mock
          </button>
          <button
            type="button"
            className={preferences.useRealPlanner ? 'segment active' : 'segment'}
            onClick={() => onPreferenceChange('useRealPlanner', true)}
            aria-pressed={preferences.useRealPlanner}
          >
            Ollama
          </button>
        </div>
        {preferences.useRealPlanner ? (
          <span className="pref-hint">{plannerReady ? 'prêt' : 'warmup…'}</span>
        ) : null}
      </div>

      <div className="pref-group pref-group--theme">
        <span className="pref-label">Thème</span>
        <select
          className="theme-select"
          value={preferences.theme}
          onChange={(e) => onPreferenceChange('theme', e.target.value)}
          aria-label="Thème"
        >
          <option value="dark">Sombre</option>
          <option value="light">Clair</option>
        </select>
      </div>
    </div>
  )
}
