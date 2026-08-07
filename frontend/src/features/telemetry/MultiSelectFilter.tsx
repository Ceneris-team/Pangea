interface Option {
  id: string
  name: string
}

interface MultiSelectFilterProps {
  label: string
  options: Option[]
  selectedIds: string[]
  onToggle: (id: string) => void
}

function MultiSelectFilter({ label, options, selectedIds, onToggle }: MultiSelectFilterProps) {
  return (
    <fieldset className="filter-group">
      <legend>{label}</legend>
      <div className="filter-options">
        {options.map((option) => (
          <label key={option.id} className="filter-option">
            <input
              type="checkbox"
              checked={selectedIds.includes(option.id)}
              onChange={() => onToggle(option.id)}
            />
            {option.name}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export default MultiSelectFilter
