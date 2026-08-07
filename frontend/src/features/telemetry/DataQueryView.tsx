import { useState } from 'react'
import MultiSelectFilter from './MultiSelectFilter'
import { mockLocations, mockParameters, mockReadings } from './mockData'
import './DataQueryView.css'

function DataQueryView() {
  const [draftParameterIds, setDraftParameterIds] = useState<string[]>([])
  const [draftLocationIds, setDraftLocationIds] = useState<string[]>([])
  const [appliedParameterIds, setAppliedParameterIds] = useState<string[]>([])
  const [appliedLocationIds, setAppliedLocationIds] = useState<string[]>([])

  const toggleParameter = (id: string) => {
    setDraftParameterIds((current) =>
      current.includes(id) ? current.filter((p) => p !== id) : [...current, id],
    )
  }

  const toggleLocation = (id: string) => {
    setDraftLocationIds((current) =>
      current.includes(id) ? current.filter((l) => l !== id) : [...current, id],
    )
  }

  const handleApply = () => {
    setAppliedParameterIds(draftParameterIds)
    setAppliedLocationIds(draftLocationIds)
  }

  const handleClear = () => {
    setDraftParameterIds([])
    setDraftLocationIds([])
    setAppliedParameterIds([])
    setAppliedLocationIds([])
  }

  // Si no hay filtros aplicados, se muestran todos los registros disponibles.
  const visibleReadings = mockReadings.filter((reading) => {
    const matchesParameter =
      appliedParameterIds.length === 0 || appliedParameterIds.includes(reading.parameterId)
    const matchesLocation =
      appliedLocationIds.length === 0 || appliedLocationIds.includes(reading.locationId)
    return matchesParameter && matchesLocation
  })

  const parameterName = (id: string) => mockParameters.find((p) => p.id === id)?.name ?? id
  const locationName = (id: string) => mockLocations.find((l) => l.id === id)?.name ?? id

  return (
    <section className="data-query-view">
      <h1>HU13 - Consulta de datos de telemetría</h1>

      <div className="filters-panel">
        <MultiSelectFilter
          label="Parámetros"
          options={mockParameters}
          selectedIds={draftParameterIds}
          onToggle={toggleParameter}
        />
        <MultiSelectFilter
          label="Ubicaciones"
          options={mockLocations}
          selectedIds={draftLocationIds}
          onToggle={toggleLocation}
        />
        <div className="filter-actions">
          <button type="button" className="btn-apply" onClick={handleApply}>
            APLICAR
          </button>
          <button type="button" className="btn-clear" onClick={handleClear}>
            LIMPIAR FILTROS
          </button>
        </div>
      </div>

      <table className="readings-table">
        <thead>
          <tr>
            <th>Parámetro</th>
            <th>Ubicación</th>
            <th>Valor</th>
            <th>Fecha</th>
          </tr>
        </thead>
        <tbody>
          {visibleReadings.map((reading, index) => (
            <tr key={`${reading.parameterId}-${reading.locationId}-${index}`}>
              <td>{parameterName(reading.parameterId)}</td>
              <td>{locationName(reading.locationId)}</td>
              <td>
                {reading.value} {reading.unit}
              </td>
              <td>{reading.timestamp}</td>
            </tr>
          ))}
          {visibleReadings.length === 0 && (
            <tr>
              <td colSpan={4}>No hay registros para los filtros seleccionados.</td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  )
}

export default DataQueryView
