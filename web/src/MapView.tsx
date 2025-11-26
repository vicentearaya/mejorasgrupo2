import React, { useCallback, useState } from 'react'
import { GoogleMap, useJsApiLoader, Marker, Polyline, Libraries } from '@react-google-maps/api'
import PlaceAutocomplete from './components/PlaceAutocomplete'
import PlaceInfoPanel from './components/PlaceInfoPanel'
import axios from 'axios'
import TestGooglePlaces from './TestGooglePlaces'

// Ensure Google Maps types are available
/// <reference types="@types/google.maps" />

// Configuración de Google Maps
const libraries: Libraries = ['places']
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const containerStyle = {
  width: '100%',
  height: '100%'
}

const defaultCenter = { lat: -33.45, lng: -70.66 } // Santiago, Chile

interface LatLng {
  lat: number;
  lng: number;
}

interface Driver {
  id: number;
  nombre: string;
  email?: string;
  role_id: number;
  activo: boolean;
  rut?: string;
  role_name?: string;
}

interface Vehicle {
  id: string;
  name: string;
  driver_id?: number;
  currentLocation?: string;
  route?: {
    coords: LatLng[];
    distance_m: number;
    duration_s: number;
  };
}

interface RouteRequest {
  vehicleId: string;
  origin: string;
  destination: string;
  waypoints?: string[];
  timestamp: number;
  status?: string;
}

interface PlaceLocation {
  lat: number;
  lng: number;
}

interface ExtendedPlaceResult {
  geometry?: google.maps.places.PlaceGeometry;
  formatted_address: string;
  location?: PlaceLocation;
}

function decodePolyline(encoded: string) {
  let index = 0, lat = 0, lng = 0, coordinates: any[] = [];
  while (index < encoded.length) {
    let b, shift = 0, result = 0;
    do { b = encoded.charCodeAt(index++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    const dlat = ((result & 1) ? ~(result >> 1) : (result >> 1));
    lat += dlat;
    shift = 0; result = 0;
    do { b = encoded.charCodeAt(index++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    const dlng = ((result & 1) ? ~(result >> 1) : (result >> 1));
    lng += dlng;
    coordinates.push({ lat: lat / 1e5, lng: lng / 1e5 });
  }
  return coordinates;
}

export default function MapView() {
  const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY
  if (!GOOGLE_MAPS_API_KEY) {
    console.error('Google Maps API Key no encontrada. Por favor configura VITE_GOOGLE_MAPS_API_KEY en tu archivo .env')
    throw new Error('Google Maps API Key es requerida')
  }
  const { isLoaded, loadError } = useJsApiLoader({
    id: 'google-map-script',
    googleMapsApiKey: GOOGLE_MAPS_API_KEY as string,
    libraries
  })

  const [map, setMap] = useState<google.maps.Map | null>(null)
  const [drivers, setDrivers] = useState<Driver[]>([])
  const [selectedDriver, setSelectedDriver] = useState<number | null>(null)
  const [loadingDrivers, setLoadingDrivers] = useState(false)
  const [originPlace, setOriginPlace] = useState<ExtendedPlaceResult | null>(null)
  const [destPlace, setDestPlace] = useState<ExtendedPlaceResult | null>(null)
  const [route, setRoute] = useState<{ coords: google.maps.LatLngLiteral[]; distance_m: number; duration_s: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [requests, setRequests] = useState<RouteRequest[]>([])
  const [waypointsInput, setWaypointsInput] = useState<string>('')
  const [intermediateStops, setIntermediateStops] = useState<ExtendedPlaceResult[]>([])
  const [isMapLoaded, setIsMapLoaded] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [mapsLoaded, setMapsLoaded] = useState(false)
  // Estado para el panel de información de lugares
  const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null)
  const [selectedPlaceData, setSelectedPlaceData] = useState<any>(null)
  // Estado para ruta pendiente de confirmación
  const [pendingRoute, setPendingRoute] = useState<any>(null)
  const [confirmingRoute, setConfirmingRoute] = useState(false)

  // Cargar conductores desde la BD al iniciar
  const loadDriversFromDB = async () => {
    try {
      setLoadingDrivers(true)
      console.log('🔄 Cargando empleados desde PostgreSQL...')
      const res = await axios.get('/api/rrhh/employees/')

      if (res.data && Array.isArray(res.data)) {
        const dbDrivers: Driver[] = res.data.map((d: any) => ({
          id: d.id,
          nombre: d.nombre,
          email: d.email,
          role_id: d.role_id,
          activo: d.activo,
          rut: d.rut,
          role_name: d.role_name || 'Empleado'
        }))

        setDrivers(dbDrivers)
        console.log(`✅ Empleados cargados: ${dbDrivers.length}`, dbDrivers)

        // Si hay empleados, seleccionar el primero por defecto
        if (dbDrivers.length > 0 && !selectedDriver) {
          setSelectedDriver(dbDrivers[0].id)
          console.log(`✅ Empleado seleccionado por defecto: ${dbDrivers[0].nombre} (ID: ${dbDrivers[0].id})`)
        }
      }
    } catch (err: any) {
      console.error('❌ Error al cargar empleados:', err)
      setError(`Error al cargar empleados: ${err.message}`)
    } finally {
      setLoadingDrivers(false)
    }
  }

  // Cargar conductores al montar el componente
  React.useEffect(() => {
    loadDriversFromDB()
  }, [])

  const onLoad = useCallback(function callback(mapInstance: google.maps.Map) {
    setMap(mapInstance)
    setIsMapLoaded(true)
  }, [])

  const onUnmount = useCallback(function callback() {
    setMap(null)
    setIsMapLoaded(false)
  }, [])

  // Manejador de clics en el mapa para detectar lugares
  const handleMapClick = useCallback(async (e: google.maps.MapMouseEvent) => {
    if (!e.latLng || !map) return;

    const clickedLocation = e.latLng;
    const service = new google.maps.places.PlacesService(map);

    // Buscar lugares cerca del punto clickeado
    service.nearbySearch(
      {
        location: clickedLocation,
        radius: 50, // 50 metros de radio
        type: 'establishment' // Solo establecimientos
      },
      (results, status) => {
        if (status === google.maps.places.PlacesServiceStatus.OK && results && results.length > 0) {
          // Tomar el primer resultado (el más cercano)
          const place = results[0];
          console.log('Lugar detectado:', place.name, place.place_id);

          // Crear información básica del lugar
          const basicPlaceInfo = {
            place_id: place.place_id,
            name: place.name,
            formatted_address: place.vicinity,
            rating: place.rating,
            user_ratings_total: place.user_ratings_total,
            types: place.types,
            geometry: {
              location: {
                lat: place.geometry?.location?.lat() || clickedLocation.lat(),
                lng: place.geometry?.location?.lng() || clickedLocation.lng()
              }
            }
          };

          setSelectedPlaceData(basicPlaceInfo);
          if (place.place_id) {
            setSelectedPlaceId(place.place_id);
          }
        } else {
          // Si no se encuentra un lugar específico, crear información básica de coordenadas
          const basicLocationInfo = {
            name: "Ubicación seleccionada",
            formatted_address: `${clickedLocation.lat().toFixed(6)}, ${clickedLocation.lng().toFixed(6)}`,
            geometry: {
              location: {
                lat: clickedLocation.lat(),
                lng: clickedLocation.lng()
              }
            },
            types: ["point_of_interest"]
          };

          setSelectedPlaceData(basicLocationInfo);
          setSelectedPlaceId("custom_location");
        }
      }
    );
  }, [map]);

  const handleClosePlaceInfo = () => {
    setSelectedPlaceId(null);
    setSelectedPlaceData(null);
  };

  const handleOriginPlaceSelect = (place: google.maps.places.PlaceResult) => {
    if (place.formatted_address && place.geometry?.location) {
      const location: PlaceLocation = {
        lat: place.geometry.location.lat(),
        lng: place.geometry.location.lng()
      };
      setOriginPlace({
        geometry: place.geometry,
        formatted_address: place.formatted_address,
        location
      });
      // Recenter map to selected origin
      if (map) {
        map.panTo(location as google.maps.LatLngLiteral);
        map.setZoom(14);
      }
    }
  }

  const handleDestPlaceSelect = (place: google.maps.places.PlaceResult) => {
    if (place.formatted_address && place.geometry?.location) {
      const location: PlaceLocation = {
        lat: place.geometry.location.lat(),
        lng: place.geometry.location.lng()
      };
      setDestPlace({
        geometry: place.geometry,
        formatted_address: place.formatted_address,
        location
      });
      // Recenter map to selected destination
      if (map) {
        map.panTo(location as google.maps.LatLngLiteral);
        map.setZoom(14);
      }
    }
  }

  const addDriver = () => {
    loadDriversFromDB()
  }

  const addIntermediateStop = () => {
    setIntermediateStops([...intermediateStops, null as any])
  }

  const removeIntermediateStop = (index: number) => {
    setIntermediateStops(intermediateStops.filter((_, i) => i !== index))
  }

  const handleIntermediateStopSelect = (index: number, place: google.maps.places.PlaceResult) => {
    const extended = {
      ...place,
      formatted_address: place.formatted_address || place.name || '',
      lat: place.geometry?.location?.lat() || 0,
      lng: place.geometry?.location?.lng() || 0
    }
    const newStops = [...intermediateStops]
    newStops[index] = extended
    setIntermediateStops(newStops)
  }

  // Función para confirmar y guardar la ruta en BD + RR.HH.
  const confirmRoute = async () => {
    if (!pendingRoute) {
      setError('No hay ruta pendiente para confirmar')
      return
    }

    try {
      setConfirmingRoute(true)
      console.log('💾 Confirmando y guardando ruta en PostgreSQL...')

      const assignPayload = {
        driver_id: pendingRoute.driver_id,
        driver_name: pendingRoute.driver_name,
        origin: pendingRoute.origin,
        destination: pendingRoute.destination,
        route_data: {
          polyline: pendingRoute.polyline,
          distance_m: pendingRoute.distance_m,
          duration_s: pendingRoute.duration_s,
          waypoints: pendingRoute.waypoints
        }
      }

      const assignRes = await axios.post(API_URL + '/api/routes/assign', assignPayload)

      if (assignRes.data.success) {
        console.log('✅ Ruta confirmada y guardada:', assignRes.data.tracking_number)

        // Intentar sincronizar con RR.HH. (dinámico)
        try {
          const rrhhPayload = {
            tracking_number: assignRes.data.tracking_number,
            driver_id: pendingRoute.driver_id,
            driver_name: pendingRoute.driver_name,
            route_data: {
              origin: pendingRoute.origin,
              destination: pendingRoute.destination,
              distance_m: pendingRoute.distance_m,
              duration_s: pendingRoute.duration_s,
              estimated_start: new Date().toISOString()
            }
          }

          await axios.post(API_URL + '/api/rrhh/sync-route', rrhhPayload)
          console.log('✅ Sincronizado con RR.HH.')
        } catch (rrhhError) {
          console.warn('⚠️ No se pudo sincronizar con RR.HH. (servicio no disponible)', rrhhError)
          // No es error crítico - continuar
        }

        // Limpiar ruta pendiente
        setPendingRoute(null)
        setError(null)
        alert(`✅ Ruta confirmada exitosamente!\nTracking: ${assignRes.data.tracking_number}`)
      }
    } catch (dbError: any) {
      console.error('❌ Error al confirmar ruta:', dbError)
      const dbErrorMsg = dbError?.response?.data?.detail
        || dbError?.response?.data?.message
        || dbError.message
        || 'Error al guardar en base de datos'
      setError(`Error al confirmar ruta: ${dbErrorMsg}`)
    } finally {
      setConfirmingRoute(false)
    }
  }

  const computeRoute = async () => {
    if (!originPlace || !destPlace) {
      return
    }

    if (!selectedDriver && drivers.length === 0) {
      setError('⚠️ Debes asignar un conductor primero')
      console.warn('No hay conductores disponibles')
      return
    }

    if (!selectedDriver) {
      setError('⚠️ Selecciona un conductor de la lista')
      console.warn('Conductor no seleccionado')
      return
    }

    const currentDriver = drivers.find(d => d.id === selectedDriver)

    if (!currentDriver) {
      setError('⚠️ Conductor no encontrado')
      console.error('Conductor no encontrado con ID:', selectedDriver)
      return
    }

    setIsLoading(true)
    console.log(`🚀 Calculando ruta para ${currentDriver.nombre}...`)

    const waypoints = waypointsInput
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0)

    // Combinar paradas intermedias de la nueva UI
    const modernWaypoints = intermediateStops
      .filter(stop => stop && stop.formatted_address)
      .map(stop => stop.formatted_address)

    const allWaypoints = [...waypoints, ...modernWaypoints]

    const payload = {
      origin: {
        address: originPlace.formatted_address,
        lat: originPlace.location?.lat,
        lng: originPlace.location?.lng
      },
      destination: {
        address: destPlace.formatted_address,
        lat: destPlace.location?.lat,
        lng: destPlace.location?.lng
      },
      waypoints: allWaypoints.map(address => ({ address })),
      driverId: currentDriver.id,
      driverName: currentDriver.nombre,
      optimize: true
    }

    try {
      console.log('📍 Payload:', {
        origen: payload.origin.address,
        destino: payload.destination.address,
        paradas: allWaypoints.length,
        conductor: payload.driverName
      })

      const res = await axios.post(API_URL + '/maps/directions', payload)

      // Validar respuesta
      if (!res.data) {
        throw new Error('Respuesta vacía del servidor')
      }

      const poly = res.data.polyline
      if (!poly || typeof poly !== 'string') {
        throw new Error('Polyline no válido en respuesta')
      }

      const coords = decodePolyline(poly)

      if (!Array.isArray(coords) || coords.length === 0) {
        throw new Error('No se pudo decodificar la ruta')
      }

      const routeInfo = {
        coords,
        distance_m: res.data.distance_m || 0,
        duration_s: res.data.duration_s || 0,
        waypoints: res.data.waypoints || []
      }

      setRoute(routeInfo)
      console.log(`✓ Ruta calculada: ${(routeInfo.distance_m / 1000).toFixed(2)}km, ${Math.round(routeInfo.duration_s / 60)}min`)

      if (coords && coords.length > 0 && map) {
        try {
          const bounds = new window.google.maps.LatLngBounds()
          coords.forEach((p: any) => {
            if (p && p.lat && p.lng) {
              bounds.extend({ lat: p.lat, lng: p.lng })
            }
          })
          map.fitBounds(bounds)
          console.log('✓ Mapa ajustado a la ruta')
        } catch (boundsError) {
          console.warn('⚠️ Error al ajustar bounds del mapa:', boundsError)
        }
      }

      // Guardar la solicitud con información del conductor
      const newRequest: RouteRequest = {
        vehicleId: `DRIVER-${currentDriver.id}`,
        origin: originPlace.formatted_address,
        destination: destPlace.formatted_address,
        waypoints: allWaypoints,
        timestamp: Date.now(),
        status: 'completed'
      }
      setRequests([newRequest, ...requests])
      console.log('✓ Solicitud guardada en frontend:', newRequest)

      // ✅ GUARDAR TEMPORALMENTE PARA CONFIRMACIÓN
      // Guardar datos de la ruta calculada para el botón "Aceptar Ruta"
      setPendingRoute({
        driver_id: currentDriver.id,
        driver_name: currentDriver.nombre,
        origin: originPlace.formatted_address,
        destination: destPlace.formatted_address,
        distance_m: routeInfo.distance_m,
        duration_s: routeInfo.duration_s,
        polyline: res.data.polyline,
        waypoints: allWaypoints
      })

      console.log('📋 Ruta calculada y lista para confirmar')
      setError(null) // Limpiar errores previos

    } catch (e: any) {
      console.error('❌ Error al calcular ruta:', e)
      const errorMsg = e?.response?.data?.detail
        || e?.response?.data?.message
        || e.message
        || 'Error desconocido al calcular la ruta'
      setError(`Error: ${errorMsg}`)

      // Log detallado para debugging
      if (e?.response) {
        console.error('Respuesta del servidor:', {
          status: e.response.status,
          data: e.response.data
        })
      }
    } finally {
      setIsLoading(false)
    }
  }

  if (loadError) {
    return (
      <div style={{ padding: 16 }}>
        <div style={{ color: 'red' }}>Error cargando Google Maps: {String(loadError)}</div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', height: '100%' }} >
      <div style={{ width: 360, padding: 12, boxSizing: 'border-box' }}>
        <div style={{ marginBottom: '10px' }}>
          <button
            onClick={addDriver}
            disabled={loadingDrivers}
            className="px-4 py-2 bg-blue-600 text-white rounded border border-blue-700 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {loadingDrivers ? '⏳ Cargando...' : '🔄 Recargar Conductores'}
          </button>
          {drivers.length > 0 && (
            <select
              id="driver-select"
              name="driver"
              value={selectedDriver || ''}
              onChange={(e) => setSelectedDriver(Number(e.target.value))}
              className="ml-2.5 px-3 py-2 border border-gray-300 rounded w-full mt-2"
            >
              <option value="">Seleccionar conductor...</option>
              {drivers.map(driver => (
                <option key={driver.id} value={driver.id}>
                  👤 {driver.nombre} {driver.rut ? `(${driver.rut})` : ''}
                </option>
              ))}
            </select>
          )}
          {loadingDrivers && <div style={{ fontSize: '12px', color: '#666', marginTop: '5px' }}>Conectando con PostgreSQL...</div>}
        </div>

        <div>
          <h4>Origen</h4>
          {isLoaded ? (
            <PlaceAutocomplete
              onPlaceSelect={handleOriginPlaceSelect}
              googleMapsApiKey={GOOGLE_MAPS_API_KEY || ''}
              placeholder="Buscar dirección de origen..."
            />
          ) : (
            <div style={{ fontSize: 12, color: '#666' }}>Cargando Google Maps…</div>
          )}

          <h4>Destino</h4>
          {isLoaded ? (
            <PlaceAutocomplete
              onPlaceSelect={handleDestPlaceSelect}
              googleMapsApiKey={GOOGLE_MAPS_API_KEY || ''}
              placeholder="Buscar dirección de destino..."
            />
          ) : null}

          <h4>Paradas intermedias (opcional)</h4>

          {/* Nueva UI para paradas intermedias */}
          {intermediateStops.map((stop, index) => (
            <div key={index} style={{ display: 'flex', marginBottom: '8px', alignItems: 'center' }}>
              <div style={{ flex: 1, marginRight: '8px' }}>
                {isLoaded ? (
                  <PlaceAutocomplete
                    onPlaceSelect={(place) => handleIntermediateStopSelect(index, place)}
                    googleMapsApiKey={GOOGLE_MAPS_API_KEY || ''}
                    placeholder={`Parada ${index + 1}...`}
                  />
                ) : (
                  <input
                    type="text"
                    placeholder={`Parada ${index + 1}...`}
                    style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                  />
                )}
              </div>
              <button
                onClick={() => removeIntermediateStop(index)}
                style={{
                  background: '#ef4444',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  padding: '8px',
                  cursor: 'pointer',
                  fontSize: '14px'
                }}
                title="Eliminar parada"
              >
                ✕
              </button>
            </div>
          ))}

          <button
            onClick={addIntermediateStop}
            style={{
              background: '#10b981',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              padding: '8px 12px',
              cursor: 'pointer',
              marginBottom: '10px',
              fontSize: '14px'
            }}
          >
            + Agregar parada
          </button>

          {/* Textarea legacy para compatibilidad */}
          <details style={{ marginBottom: '10px' }}>
            <summary style={{ cursor: 'pointer', fontSize: '12px', color: '#666' }}>Modo texto (avanzado)</summary>
            <textarea
              id="waypoints"
              name="waypoints"
              value={waypointsInput}
              onChange={(e) => setWaypointsInput(e.target.value)}
              placeholder="Una dirección por línea"
              style={{ width: '100%', minHeight: '60px', marginTop: '8px' }}
            />
          </details>

          <button
            onClick={computeRoute}
            disabled={!originPlace || !destPlace || !selectedDriver || isLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded border border-blue-700 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed mt-2.5 w-full"
          >
            {isLoading ? 'Calculando...' : 'Calcular Ruta'}
          </button>

          {/* Botón para confirmar y guardar ruta */}
          {pendingRoute && (
            <button
              onClick={confirmRoute}
              disabled={confirmingRoute}
              className="px-4 py-2 bg-green-600 text-white rounded border border-green-700 hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed mt-2.5 w-full"
              style={{ marginTop: '10px' }}
            >
              {confirmingRoute ? '⏳ Guardando...' : '✅ Aceptar y Guardar Ruta'}
            </button>
          )}

          {pendingRoute && (
            <div style={{
              fontSize: '11px',
              background: '#d4edda',
              padding: '8px',
              borderRadius: '4px',
              marginTop: '10px',
              border: '1px solid #c3e6cb',
              color: '#155724'
            }}>
              <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>✓ Ruta calculada - Lista para confirmar</div>
              <div>📏 {(pendingRoute.distance_m / 1000).toFixed(2)} km</div>
              <div>⏱️ {Math.round(pendingRoute.duration_s / 60)} minutos</div>
            </div>
          )}

          {/* Panel de estado */}
          <div style={{
            fontSize: '11px',
            background: '#f8f9fa',
            padding: '8px',
            borderRadius: '4px',
            marginTop: '10px',
            border: '1px solid #e9ecef'
          }}>
            <div style={{ fontWeight: 'bold', marginBottom: '4px', color: '#495057' }}>Estado:</div>
            <div style={{ color: originPlace ? '#28a745' : '#6c757d' }}>
              {originPlace ? '✓' : '○'} Origen: {originPlace?.formatted_address?.substring(0, 30) || 'No seleccionado'}
            </div>
            <div style={{ color: destPlace ? '#28a745' : '#6c757d' }}>
              {destPlace ? '✓' : '○'} Destino: {destPlace?.formatted_address?.substring(0, 30) || 'No seleccionado'}
            </div>
            <div style={{ color: selectedDriver ? '#28a745' : '#6c757d' }}>
              {selectedDriver ? '✓' : '○'} Conductor: {drivers.find((d: Driver) => d.id === selectedDriver)?.nombre || 'No asignado'}
            </div>
            {intermediateStops.length > 0 && (
              <div style={{ color: '#17a2b8' }}>
                ⊕ Paradas intermedias: {intermediateStops.filter(s => s).length}
              </div>
            )}
          </div>

          {error && (
            <div style={{
              color: '#721c24',
              background: '#f8d7da',
              border: '1px solid #f5c6cb',
              padding: '10px',
              borderRadius: '4px',
              marginTop: '10px',
              fontSize: '13px'
            }}>
              ⚠️ {error}
            </div>
          )}

          {route && (
            <div style={{ marginTop: '10px' }}>
              <h4>Detalles de la ruta:</h4>
              <p>Distancia: {(route.distance_m / 1000).toFixed(2)} km</p>
              <p>Duración estimada: {Math.round(route.duration_s / 60)} minutos</p>
            </div>
          )}
        </div>

        <div style={{ marginTop: '20px' }}>
          <h4>Solicitudes de ruta</h4>
          <div style={{ maxHeight: '200px', overflow: 'auto' }}>
            {requests.map((req, index) => (
              <div key={index} style={{ padding: '10px', borderBottom: '1px solid #eee' }}>
                <div><strong>Conductor:</strong> {drivers.find(d => d.id === parseInt(req.vehicleId.replace('DRIVER-', '')))?.nombre || req.vehicleId}</div>
                <div><strong>Origen:</strong> {req.origin}</div>
                <div><strong>Destino:</strong> {req.destination}</div>
                <div><strong>Estado:</strong> {req.status}</div>
                <div><small>{new Date(req.timestamp).toLocaleString()}</small></div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ flex: 1 }}>
        {isLoaded ? (
          <GoogleMap
            mapContainerStyle={containerStyle}
            center={defaultCenter}
            zoom={12}
            onLoad={onLoad}
            onUnmount={onUnmount}
            onClick={handleMapClick}
            options={{
              zoomControl: true,
              mapTypeControl: true,
              scaleControl: true,
              streetViewControl: true,
              rotateControl: true,
              fullscreenControl: true
            }}
          >
            {originPlace?.location && (
              <Marker
                position={originPlace.location}
                title="Origen"
              />
            )}
            {destPlace?.location && (
              <Marker
                position={destPlace.location}
                title="Destino"
              />
            )}
            {route && (
              <Polyline
                path={route.coords}
                options={{
                  strokeColor: '#1976D2',
                  strokeWeight: 4
                }}
              />
            )}
          </GoogleMap>
        ) : (
          <div style={{ padding: 16, color: '#666' }}>Cargando mapa…</div>
        )}

        {/* Panel de información de lugares */}
        {(selectedPlaceId || selectedPlaceData) && (
          <PlaceInfoPanel
            placeId={selectedPlaceId}
            placeData={selectedPlaceData}
            onClose={handleClosePlaceInfo}
            googleMapsApiKey={GOOGLE_MAPS_API_KEY}
          />
        )}
      </div>
    </div >
  )
}