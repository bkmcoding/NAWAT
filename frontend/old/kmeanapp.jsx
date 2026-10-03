import { useState } from 'react';
import Map, { Source, Layer, Marker } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

export default function App() {
  const [mapData, setMapData] = useState({ tileUrl: null, metrics: null });
  const [isLoading, setIsLoading] = useState(false);

  const handleAnalyzeFire = async () => {
    setIsLoading(true);
    setMapData({ tileUrl: null, metrics: null }); 
    
    try {
      const response = await fetch('http://localhost:8000/api/analyze-fire', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lng: -121.3283, lat: 40.0632, radius_meters: 30000,
          pre_fire_start: '2021-06-01', pre_fire_end: '2021-07-01',
          post_fire_start: '2021-09-15', post_fire_end: '2021-10-15'
        })
      });
      
      const data = await response.json();
      if (data.status === 'success') {
        setMapData({ tileUrl: data.tile_url, metrics: data.metrics });
      }
    } catch (error) {
      console.error("Failed to fetch fire data:", error);
    }
    setIsLoading(false);
  };

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative' }}>
      
      {/* Injecting a quick CSS animation for the pulsing markers */}
      <style>{`
        @keyframes pulse {
          0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 69, 0, 0.7); }
          70% { transform: scale(1); box-shadow: 0 0 0 15px rgba(255, 69, 0, 0); }
          100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 69, 0, 0); }
        }
        .cluster-marker {
          width: 16px; height: 16px;
          background-color: #ff4500;
          border: 2px solid white;
          border-radius: 50%;
          animation: pulse 2s infinite;
          cursor: pointer;
        }
      `}</style>

      {/* Analytics Dashboard Panel */}
      <div style={{
        position: 'absolute', top: 20, left: 20, zIndex: 10, width: '320px',
        backgroundColor: '#1e1e1e', color: 'white', padding: '20px', 
        borderRadius: '8px', fontFamily: 'sans-serif', boxShadow: '0 4px 15px rgba(0,0,0,0.5)'
      }}>
        <h2 style={{ margin: '0 0 15px 0', fontSize: '20px' }}>Wildfire Analytics</h2>
        <button 
          onClick={handleAnalyzeFire} disabled={isLoading}
          style={{
            padding: '12px 20px', cursor: 'pointer', fontWeight: 'bold', fontSize: '14px',
            backgroundColor: isLoading ? '#555' : '#ff4500', 
            color: 'white', border: 'none', borderRadius: '4px', width: '100%',
            transition: 'background-color 0.3s'
          }}
        >
          {isLoading ? 'Running ML Models...' : 'Analyze Dixie Fire'}
        </button>

        {/* Dynamic Results Section */}
        {mapData.metrics && (
          <div style={{ 
            marginTop: '20px', padding: '15px', 
            backgroundColor: '#2a2a2a', borderRadius: '6px', borderLeft: '4px solid #ff4500'
          }}>
            <h3 style={{ margin: '0 0 10px 0', fontSize: '16px', color: '#ff4500' }}>Damage Report</h3>
            
            <div style={{ marginBottom: '10px' }}>
              <span style={{ fontSize: '12px', color: '#aaa', textTransform: 'uppercase' }}>Catastrophic Loss Area</span>
              <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
                {mapData.metrics.high_severity_acres.toLocaleString()} <span style={{ fontSize: '14px', fontWeight: 'normal', color: '#ccc' }}>acres</span>
              </div>
            </div>

            <p style={{ margin: '10px 0 0 0', fontSize: '12px', color: '#aaa', lineHeight: '1.4' }}>
              <strong>K-Means Clustering:</strong> Map markers indicate the 5 primary epicenters of extreme severity to guide recovery deployment.
            </p>
          </div>
        )}
      </div>

      <Map
        initialViewState={{ longitude: -121.3283, latitude: 40.0632, zoom: 9.5 }}
        mapStyle="mapbox://styles/mapbox/dark-v11"
        mapboxAccessToken={MAPBOX_TOKEN}
      >
        {mapData.tileUrl && (
          <Source id="earth-engine-raster" type="raster" tiles={[mapData.tileUrl]} tileSize={256}>
            <Layer id="dnbr-overlay" type="raster" paint={{ 'raster-opacity': 0.7 }} />
          </Source>
        )}

        {mapData.metrics?.epicenters?.map((center, index) => (
          <Marker 
            key={index} 
            longitude={center.lng} 
            latitude={center.lat} 
            anchor="center"
          >
            <div className="cluster-marker" title="Catastrophic Epicenter"></div>
          </Marker>
        ))}
      </Map>

    </div>
  );
}