import { useState } from 'react';
import Map, { Source, Layer } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

const MAPBOX_TOKEN = import.meta.env.MAPBOX_TOKEN;;

export default function App() {
  const [tileUrl, setTileUrl] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleAnalyzeFire = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/analyze-fire', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lng: -121.3283,
          lat: 40.0632,
          radius_meters: 30000,
          pre_fire_start: '2021-06-01',
          pre_fire_end: '2021-07-01',
          post_fire_start: '2021-09-15',
          post_fire_end: '2021-10-15'
        })
      });
      
      const data = await response.json();
      if (data.status === 'success') {
        setTileUrl(data.tile_url);
      }
    } catch (error) {
      console.error("Failed to fetch fire data:", error);
    }
    setIsLoading(false);
  };

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative' }}>
      
      {}
      <div style={{
        position: 'absolute', top: 20, left: 20, zIndex: 10,
        backgroundColor: '#1e1e1e', color: 'white', padding: '20px', 
        borderRadius: '8px', fontFamily: 'sans-serif'
      }}>
        <h2>NAWAT: North American Wildfire Analysis Tool</h2>
        <button 
          onClick={handleAnalyzeFire}
          disabled={isLoading}
          style={{
            padding: '10px 20px', cursor: 'pointer',
            backgroundColor: isLoading ? '#555' : '#ff4500', 
            color: 'white', border: 'none', borderRadius: '4px'
          }}
        >
          {isLoading ? 'Processing Satellite Data...' : 'Load Dixie Fire (2021)'}
        </button>
      </div>

      {}
      <Map
        initialViewState={{
          longitude: -121.3283,
          latitude: 40.0632,
          zoom: 9
        }}
        mapStyle="mapbox://styles/mapbox/dark-v11"
        mapboxAccessToken={MAPBOX_TOKEN}
      >
        {}
        {tileUrl && (
          <Source id="earth-engine" type="raster" tiles={[tileUrl]} tileSize={256}>
            <Layer 
              id="dnbr-overlay" 
              type="raster" 
              paint={{ 'raster-opacity': 0.8 }} 
            />
          </Source>
        )}
      </Map>

    </div>
  );
}