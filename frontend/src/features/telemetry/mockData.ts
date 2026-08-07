export interface Parameter {
  id: string
  name: string
}

export interface Location {
  id: string
  name: string
}

export interface Reading {
  parameterId: string
  locationId: string
  value: number
  unit: string
  timestamp: string
}

// Simula los parámetros y ubicaciones asignados al Cliente Final por el
// Administrador (lógica de HU21) y el catálogo de parámetros de HU06.
export const mockParameters: Parameter[] = [
  { id: 'temp', name: 'Temperatura' },
  { id: 'hum', name: 'Humedad' },
  { id: 'co2', name: 'CO2' },
  { id: 'press', name: 'Presión' },
]

export const mockLocations: Location[] = [
  { id: 'alm-1', name: 'Almacén 1' },
  { id: 'alm-2', name: 'Almacén 2' },
  { id: 'puerto-callao', name: 'Puerto Callao' },
]

export const mockReadings: Reading[] = [
  { parameterId: 'temp', locationId: 'alm-1', value: 21.4, unit: '°C', timestamp: '2026-08-07 08:00' },
  { parameterId: 'temp', locationId: 'alm-2', value: 19.8, unit: '°C', timestamp: '2026-08-07 08:00' },
  { parameterId: 'hum', locationId: 'alm-1', value: 55, unit: '%', timestamp: '2026-08-07 08:00' },
  { parameterId: 'hum', locationId: 'puerto-callao', value: 68, unit: '%', timestamp: '2026-08-07 08:00' },
  { parameterId: 'co2', locationId: 'alm-2', value: 410, unit: 'ppm', timestamp: '2026-08-07 08:00' },
  { parameterId: 'press', locationId: 'puerto-callao', value: 1013, unit: 'hPa', timestamp: '2026-08-07 08:00' },
]
