import { useState } from 'react';
import Map, { Source, Layer } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

export default function App() {
  const [mapData, setMapData] = useState({ tiles: null, metrics: null });
  const [activeLayer, setActiveLayer] = useState('burn_severity');
  const [isLoading, setIsLoading] = useState(false);

  const handleAnalyzeFire = async () => {
    setIsLoading(true);
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
        setMapData({ tiles: data.tiles, metrics: data.metrics });
        setActiveLayer('burn_severity'); // Reset to burn layer on new load
      }
    } catch (error) {
      console.error("Failed to fetch fire data:", error);
    }
    setIsLoading(false);
  };

  // Helper to calculate percentages for the CSS bar charts
  const getPercentage = (value, total) => {
    if (!total) return 0;
    return Math.round((value / total) * 100);
  };

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative', backgroundColor: '#111' }}>
      
      {/* Analytics Dashboard Panel */}
      <div style={{
        position: 'absolute', top: 20, left: 20, zIndex: 10, width: '360px',
        backgroundColor: '#1e1e1e', color: 'white', padding: '24px', 
        borderRadius: '12px', fontFamily: 'sans-serif', boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        maxHeight: '90vh', overflowY: 'auto'
      }}>
        <h2 style={{ margin: '0 0 20px 0', fontSize: '22px', borderBottom: '1px solid #333', paddingBottom: '15px' }}>
          Wildfire Analytics
        </h2>
        
        <button 
          onClick={handleAnalyzeFire} disabled={isLoading}
          style={{
            padding: '14px 20px', cursor: 'pointer', fontWeight: 'bold', fontSize: '15px',
            backgroundColor: isLoading ? '#555' : '#ff4500', 
            color: 'white', border: 'none', borderRadius: '6px', width: '100%',
            transition: 'background-color 0.2s', marginBottom: '20px'
          }}
        >
          {isLoading ? 'Extracting Terrain Data...' : 'Analyze Dixie Fire'}
        </button>

        {mapData.metrics && (
          <div style={{ animation: 'fadeIn 0.5s ease-in' }}>
            
            {/* Layer Toggle Control */}
            <div style={{ display: 'flex', backgroundColor: '#000', borderRadius: '6px', padding: '4px', marginBottom: '25px' }}>
              <button 
                onClick={() => setActiveLayer('burn_severity')}
                style={{
                  flex: 1, padding: '10px', cursor: 'pointer', border: 'none', borderRadius: '4px',
                  backgroundColor: activeLayer === 'burn_severity' ? '#333' : 'transparent',
                  color: activeLayer === 'burn_severity' ? '#fff' : '#888',
                  fontWeight: activeLayer === 'burn_severity' ? 'bold' : 'normal'
                }}
              >
                Burn Severity
              </button>
              <button 
                onClick={() => setActiveLayer('topography_slope')}
                style={{
                  flex: 1, padding: '10px', cursor: 'pointer', border: 'none', borderRadius: '4px',
                  backgroundColor: activeLayer === 'topography_slope' ? '#333' : 'transparent',
                  color: activeLayer === 'topography_slope' ? '#fff' : '#888',
                  fontWeight: activeLayer === 'topography_slope' ? 'bold' : 'normal'
                }}
              >
                Terrain Slope
              </button>
            </div>

            <div style={{ marginBottom: '25px' }}>
              <span style={{ fontSize: '13px', color: '#aaa', textTransform: 'uppercase', letterSpacing: '1px' }}>Catastrophic Canopy Loss</span>
              <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#fff', marginTop: '5px' }}>
                {mapData.metrics.total_catastrophic_acres.toLocaleString()} <span style={{ fontSize: '16px', fontWeight: 'normal', color: '#888' }}>acres</span>
              </div>
            </div>

            {/* Terrain Correlation CSS Chart */}
            <h3 style={{ margin: '0 0 15px 0', fontSize: '15px', color: '#eee' }}>Topographical Driver Breakdown</h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
              
              {/* Flat Terrain Bar */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '6px' }}>
                  <span style={{ color: '#abdda4' }}>Flat (0-10°)</span>
                  <span>{getPercentage(mapData.metrics.terrain_correlation.flat_0_to_10_deg, mapData.metrics.total_catastrophic_acres)}%</span>
                </div>
                <div style={{ width: '100%', height: '8px', backgroundColor: '#333', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ 
                    width: `${getPercentage(mapData.metrics.terrain_correlation.flat_0_to_10_deg, mapData.metrics.total_catastrophic_acres)}%`, 
                    height: '100%', backgroundColor: '#abdda4', transition: 'width 1s ease-out' 
                  }}></div>
                </div>
              </div>

              {/* Moderate Terrain Bar */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '6px' }}>
                  <span style={{ color: '#fdae61' }}>Moderate (10-25°)</span>
                  <span>{getPercentage(mapData.metrics.terrain_correlation.moderate_10_to_25_deg, mapData.metrics.total_catastrophic_acres)}%</span>
                </div>
                <div style={{ width: '100%', height: '8px', backgroundColor: '#333', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ 
                    width: `${getPercentage(mapData.metrics.terrain_correlation.moderate_10_to_25_deg, mapData.metrics.total_catastrophic_acres)}%`, 
                    height: '100%', backgroundColor: '#fdae61', transition: 'width 1s ease-out' 
                  }}></div>
                </div>
              </div>

              {/* Steep Terrain Bar */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '6px' }}>
                  <span style={{ color: '#d7191c' }}>Steep (25°+)</span>
                  <span>{getPercentage(mapData.metrics.terrain_correlation.steep_25_plus_deg, mapData.metrics.total_catastrophic_acres)}%</span>
                </div>
                <div style={{ width: '100%', height: '8px', backgroundColor: '#333', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ 
                    width: `${getPercentage(mapData.metrics.terrain_correlation.steep_25_plus_deg, mapData.metrics.total_catastrophic_acres)}%`, 
                    height: '100%', backgroundColor: '#d7191c', transition: 'width 1s ease-out' 
                  }}></div>
                </div>
              </div>

            </div>
          </div>
        )}
      </div>

      <Map
        initialViewState={{ longitude: -121.3283, latitude: 40.0632, zoom: 9.5 }}
        mapStyle="mapbox://styles/mapbox/dark-v11"
        mapboxAccessToken={MAPBOX_TOKEN}
      >
        {/* We load BOTH sources but use the 'layout' property to hide the inactive one instantly */}
        
        {mapData.tiles?.burn_severity && (
          <Source id="burn-raster" type="raster" tiles={[mapData.tiles.burn_severity]} tileSize={256}>
            <Layer 
              id="burn-overlay" 
              type="raster" 
              paint={{ 'raster-opacity': 0.7 }} 
              layout={{ visibility: activeLayer === 'burn_severity' ? 'visible' : 'none' }}
            />
          </Source>
        )}

        {mapData.tiles?.topography_slope && (
          <Source id="slope-raster" type="raster" tiles={[mapData.tiles.topography_slope]} tileSize={256}>
            <Layer 
              id="slope-overlay" 
              type="raster" 
              paint={{ 'raster-opacity': 0.6 }} 
              layout={{ visibility: activeLayer === 'topography_slope' ? 'visible' : 'none' }}
            />
          </Source>
        )}
      </Map>

    </div>
  );
}