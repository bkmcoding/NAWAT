import { useEffect, useRef, useState } from 'react';
import Map, { Source, Layer } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
// Optional backend origin; falls back to the local FastAPI dev server.
// Trailing slashes are stripped so VITE_API_URL=http://host:8000/ works too.
const API_ORIGIN = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
const API_URL = `${API_ORIGIN}/api/analyze-fire`;
const FIRES_URL = `${API_ORIGIN}/api/fires`;

// Used until the catalog loads; the map then flies to the selected fire.
const FALLBACK_VIEW = { longitude: -120.86453, latitude: 40.32231, zoom: 8.6 };

const emptyMapData = () => ({
  tiles: null, metrics: null, fire: null, severity: [], landcover: null, qa: null, warnings: []
});

const PANEL_STYLE = {
  position: 'absolute', top: 20, left: 20, zIndex: 10, width: 'min(360px, calc(100% - 40px))',
  backgroundColor: '#1e1e1e', color: 'white', padding: '22px',
  borderRadius: '12px', fontFamily: 'sans-serif', boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
  maxHeight: '90vh', overflowY: 'auto'
};

const SECTION_TITLE = {
  margin: '0 0 10px 0', fontSize: '12px', color: '#bbb',
  textTransform: 'uppercase', letterSpacing: '1px'
};

const EYEBROW = {
  fontSize: '12px', color: '#aaa', textTransform: 'uppercase', letterSpacing: '1px'
};

const TERRAIN_BINS = [
  { key: 'flat_0_to_10_deg', label: 'Flat (0–10°)', color: '#abdda4' },
  { key: 'moderate_10_to_25_deg', label: 'Moderate (10–25°)', color: '#fdae61' },
  { key: 'steep_25_plus_deg', label: 'Steep (25°+)', color: '#d7191c' }
];

function formatAcres(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatPct(value) {
  return Number(value || 0).toFixed(1);
}

function formatPct2(value) {
  return Number(value || 0).toFixed(2);
}

function formatCloud(value) {
  return value == null ? 'n/a' : `${value.toFixed(1)}%`;
}

function formatNdvi(value) {
  return value == null ? 'n/a' : Number(value).toFixed(2);
}

function SeverityBreakdown({ severity }) {
  if (!severity?.length) return null;

  return (
    <div style={{ marginBottom: '22px' }}>
      <div
        style={{
          display: 'flex', height: '10px', borderRadius: '5px', overflow: 'hidden',
          marginBottom: '12px', backgroundColor: '#333'
        }}
      >
        {severity.map((row) => (
          <div
            key={row.key}
            title={`${row.label}: ${formatPct(row.pct_of_area)}%`}
            style={{ width: `${row.pct_of_area}%`, backgroundColor: row.color }}
          />
        ))}
      </div>

      {severity.map((row) => (
        <div
          key={row.key}
          style={{ display: 'flex', alignItems: 'baseline', gap: '8px', fontSize: '12px', padding: '3px 0' }}
        >
          <span
            aria-hidden="true"
            style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: row.color, flexShrink: 0 }}
          />
          <span style={{ flex: 1, color: '#ccc' }}>{row.label}</span>
          <span style={{ color: '#fff', fontVariantNumeric: 'tabular-nums' }}>{formatAcres(row.acres)} ac</span>
          <span style={{ color: '#888', width: '44px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
            {formatPct(row.pct_of_area)}%
          </span>
        </div>
      ))}
    </div>
  );
}

function QaRow({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', padding: '2px 0' }}>
      <span style={{ color: '#888' }}>{label}</span>
      <span style={{ color: '#ddd', fontVariantNumeric: 'tabular-nums' }}>{value}</span>
    </div>
  );
}

function QaPanel({ qa }) {
  if (!qa) return null;

  return (
    <div style={{ marginBottom: '22px', borderTop: '1px solid #333', paddingTop: '16px' }}>
      <h3 style={SECTION_TITLE}>Data quality</h3>
      <QaRow label="Sentinel-2 scenes" value={`${qa.pre_scenes} pre · ${qa.post_scenes} post`} />
      <QaRow
        label="Mean cloud cover"
        value={`${formatCloud(qa.pre_mean_cloud_pct)} pre · ${formatCloud(qa.post_mean_cloud_pct)} post`}
      />
      <QaRow label="Valid dNBR coverage" value={`${formatPct2(qa.valid_pct_of_area)}%`} />
      <QaRow label="Pre-fire window" value={`${qa.pre_window[0]} – ${qa.pre_window[1]}`} />
      <QaRow label="Post-fire window" value={`${qa.post_window[0]} – ${qa.post_window[1]}`} />
      {(qa.pre_fire_ndvi_mean != null || qa.pre_fire_ndvi_median != null) && (
        <QaRow
          label="Pre-fire NDVI"
          value={`${formatNdvi(qa.pre_fire_ndvi_mean)} mean · ${formatNdvi(qa.pre_fire_ndvi_median)} median`}
        />
      )}
      <p style={{ margin: '8px 0 0', fontSize: '11px', color: '#777', lineHeight: 1.4 }}>
        Scenes filtered to ≤ {qa.cloud_filter_max_pct}% cloud cover. Severity classes follow the
        USGS FireMon dNBR table and are not field-validated. NDVI is relative greenness, not biomass.
      </p>
    </div>
  );
}

function Warnings({ warnings }) {
  if (!warnings?.length) return null;

  return (
    <div
      role="status"
      style={{
        marginBottom: '20px', padding: '10px 12px', borderRadius: '6px',
        backgroundColor: '#3a2a10', border: '1px solid #7a5a1d',
        color: '#f3c97a', fontSize: '12px', lineHeight: 1.5
      }}
    >
      <div style={{ fontWeight: 'bold', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px', fontSize: '11px' }}>
        Data notes
      </div>
      <ul style={{ margin: 0, paddingLeft: '16px' }}>
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </div>
  );
}

function LandCoverPanel({ landcover }) {
  const rows = (landcover?.classes || []).filter(
    (row) => row.acres > 0 && row.pct_of_area >= 0.05
  );
  if (!rows.length) return null;

  return (
    <div style={{ marginBottom: '22px', borderTop: '1px solid #333', paddingTop: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '10px' }}>
        <h3 style={{ ...SECTION_TITLE, margin: 0 }}>Land cover</h3>
        <span style={{ fontSize: '11px', color: '#777' }}>
          {landcover.year} · {landcover.scale_m} m
        </span>
      </div>

      <div
        style={{
          display: 'flex', height: '8px', borderRadius: '4px', overflow: 'hidden',
          marginBottom: '12px', backgroundColor: '#333'
        }}
      >
        {rows.map((row) => (
          <div
            key={row.key}
            title={`${row.label}: ${formatPct(row.pct_of_area)}%`}
            style={{ width: `${row.pct_of_area}%`, backgroundColor: row.color }}
          />
        ))}
      </div>

      <div style={{ display: 'flex', fontSize: '10px', color: '#777', marginBottom: '6px' }}>
        <span style={{ flex: 1 }}>Class</span>
        <span style={{ width: '46px', textAlign: 'right' }}>Fire</span>
        <span style={{ width: '54px', textAlign: 'right' }}>High</span>
      </div>

      {rows.map((row) => (
        <div
          key={row.key}
          style={{ display: 'flex', alignItems: 'baseline', gap: '8px', fontSize: '12px', padding: '3px 0' }}
        >
          <span
            aria-hidden="true"
            style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: row.color, flexShrink: 0 }}
          />
          <span style={{ flex: 1, color: '#ccc' }}>{row.label}</span>
          <span style={{ color: '#fff', width: '46px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
            {formatPct(row.pct_of_area)}%
          </span>
          <span style={{ color: '#888', width: '54px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
            {formatPct(row.pct_of_high)}%
          </span>
        </div>
      ))}

      <p style={{ margin: '8px 0 0', fontSize: '11px', color: '#777', lineHeight: 1.4 }}>
        Share of fire area and of high-severity acres by pre-fire class. Source:{' '}
        <a href={landcover.source_url} target="_blank" rel="noreferrer" style={{ color: '#9ab' }}>
          {landcover.source}
        </a>.
      </p>
    </div>
  );
}

function TerrainBars({ metrics }) {
  const total = metrics.high_severity_acres;

  return (
    <div style={{ marginBottom: '22px' }}>
      <h3 style={SECTION_TITLE}>High-severity area by slope</h3>
      {TERRAIN_BINS.map(({ key, label, color }) => {
        const value = metrics.terrain_correlation[key] || 0;
        const pct = total ? Math.round((value / total) * 100) : 0;

        return (
          <div key={key} style={{ marginBottom: '10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
              <span style={{ color }}>{label}</span>
              <span style={{ color: '#aaa', fontVariantNumeric: 'tabular-nums' }}>
                {formatAcres(value)} ac · {pct}%
              </span>
            </div>
            <div style={{ width: '100%', height: '6px', backgroundColor: '#333', borderRadius: '3px', overflow: 'hidden' }}>
              <div style={{ width: `${pct}%`, height: '100%', backgroundColor: color, transition: 'width 0.8s ease-out' }} />
            </div>
          </div>
        );
      })}
      <p style={{ margin: '4px 0 0', fontSize: '11px', color: '#777', lineHeight: 1.4 }}>
        Percent of high-severity acres.
      </p>
    </div>
  );
}

export default function App() {
  const [mapData, setMapData] = useState(emptyMapData);
  const [activeLayer, setActiveLayer] = useState('burn_severity');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [fires, setFires] = useState([]);
  const [selectedFireId, setSelectedFireId] = useState('');
  const [catalogError, setCatalogError] = useState(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const mapRef = useRef(null);

  const selectedFire = fires.find((entry) => entry.id === selectedFireId) || null;

  useEffect(() => {
    let cancelled = false;

    const loadCatalog = async () => {
      try {
        const response = await fetch(FIRES_URL);
        if (!response.ok) {
          throw new Error(`Fire catalog failed (HTTP ${response.status}).`);
        }
        let data;
        try {
          data = await response.json();
        } catch {
          throw new Error('The fire catalog returned an invalid response.');
        }
        const entries = Array.isArray(data?.fires) ? data.fires : [];
        if (!entries.length) {
          throw new Error('The fire catalog is empty.');
        }
        if (cancelled) return;
        setFires(entries);
        setSelectedFireId((current) => current || entries[0].id);
      } catch (err) {
        if (cancelled) return;
        console.error('Failed to load fire catalog:', err);
        setCatalogError(
          err instanceof TypeError
            ? `Could not reach the analysis server at ${API_ORIGIN}. Check that the backend is running, then reload.`
            : err.message || 'Could not load the fire catalog.'
        );
      }
    };

    loadCatalog();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!mapLoaded || !selectedFire) return;
    mapRef.current?.flyTo({
      center: selectedFire.center,
      zoom: selectedFire.zoom,
      duration: 1200
    });
  }, [mapLoaded, selectedFire]);

  const handleSelectFire = (event) => {
    setSelectedFireId(event.target.value);
    setMapData(emptyMapData());
    setActiveLayer('burn_severity');
    setError(null);
  };

  const handleAnalyzeFire = async () => {
    if (!selectedFireId) {
      setError('Choose a fire before running the analysis.');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fire_id: selectedFireId })
      });

      if (!response.ok) {
        let detail = '';
        try {
          const body = await response.json();
          if (typeof body?.detail === 'string') {
            detail = body.detail;
          } else if (Array.isArray(body?.detail)) {
            detail = body.detail.map((item) => item?.msg).filter(Boolean).join('; ');
          }
        } catch {
          // Error body wasn't JSON; the status code is still useful.
        }
        throw new Error(`Analysis failed (HTTP ${response.status})${detail ? `: ${detail}` : '.'}`);
      }

      let data;
      try {
        data = await response.json();
      } catch {
        throw new Error('The analysis server returned an unexpected response.');
      }

      if (data.status !== 'success' || !data.tiles || !data.metrics || !data.severity || !data.qa) {
        throw new Error('The analysis server returned an unexpected response.');
      }

      setMapData({
        tiles: data.tiles,
        metrics: data.metrics,
        fire: data.fire,
        severity: data.severity,
        landcover: data.landcover || null,
        qa: data.qa,
        warnings: data.warnings || []
      });
      setActiveLayer('burn_severity'); // Reset to burn layer on new load
    } catch (err) {
      console.error('Failed to fetch fire data:', err);
      // Browsers throw TypeError when the request never reaches the server.
      const isNetworkError = err instanceof TypeError;
      setError(
        isNetworkError
          ? `Could not reach the analysis server at ${API_ORIGIN}. Check that the backend is running, then try again.`
          : err.message || 'The analysis failed for an unknown reason.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  const fire = mapData.fire;

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', backgroundColor: '#111' }}>

      {/* Analytics Dashboard Panel */}
      <div style={PANEL_STYLE}>
        <h2 style={{ margin: '0 0 14px 0', fontSize: '22px', borderBottom: '1px solid #333', paddingBottom: '14px' }}>
          Wildfire Analytics
        </h2>
        <p style={{ margin: '0 0 18px', fontSize: '12px', color: '#8a8a8a' }}>
          {selectedFire ? `${selectedFire.name} · ${selectedFire.year}` : 'Select a fire'}
          {' '}· Sentinel-2 dNBR
        </p>

        <div style={{ marginBottom: '14px' }}>
          <label
            htmlFor="fire-select"
            style={{
              display: 'block', fontSize: '11px', color: '#888',
              textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '6px'
            }}
          >
            Fire
          </label>
          <select
            id="fire-select"
            value={selectedFireId}
            onChange={handleSelectFire}
            disabled={isLoading || !fires.length}
            style={{
              width: '100%', padding: '10px 12px', borderRadius: '6px',
              border: '1px solid #444', backgroundColor: '#111', color: '#fff',
              fontSize: '14px', cursor: fires.length ? 'pointer' : 'not-allowed'
            }}
          >
            {!fires.length && (
              <option value="">{catalogError ? 'Catalog unavailable' : 'Loading fires...'}</option>
            )}
            {fires.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name} · {entry.year}
              </option>
            ))}
          </select>
          {selectedFire && (
            <div style={{ marginTop: '6px', fontSize: '11px', color: '#777' }}>
              {formatAcres(selectedFire.acres)} acres · started {selectedFire.alarm_date}
            </div>
          )}
          {catalogError && (
            <p role="alert" style={{ margin: '8px 0 0', color: '#fca5a5', fontSize: '12px', lineHeight: 1.4 }}>
              {catalogError}
            </p>
          )}
        </div>

        <button
          onClick={handleAnalyzeFire}
          disabled={isLoading || !selectedFireId}
          style={{
            padding: '14px 20px',
            cursor: isLoading || !selectedFireId ? 'not-allowed' : 'pointer',
            fontWeight: 'bold', fontSize: '15px',
            backgroundColor: isLoading || !selectedFireId ? '#555' : '#ff4500',
            color: 'white', border: 'none', borderRadius: '6px', width: '100%',
            transition: 'background-color 0.2s', marginBottom: '20px'
          }}
        >
          {isLoading ? 'Computing severity...' : selectedFire ? `Analyze ${selectedFire.name}` : 'Analyze fire'}
        </button>

        {error && (
          <div
            role="alert"
            style={{
              marginBottom: '20px', padding: '12px 14px', borderRadius: '6px',
              backgroundColor: '#3a1414', border: '1px solid #7f1d1d',
              color: '#fca5a5', fontSize: '13px', lineHeight: 1.5,
              textAlign: 'left', wordBreak: 'break-word'
            }}
          >
            {error}
            {mapData.metrics && (
              <div style={{ marginTop: '6px', fontSize: '11px', color: '#e0a0a0' }}>
                The map and numbers below are from the previous successful run.
              </div>
            )}
          </div>
        )}

        {mapData.metrics && (
          <div style={{ animation: 'fadeIn 0.5s ease-in' }}>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '14px' }}>
              <h3 style={{ margin: 0, fontSize: '16px' }}>{fire?.name || 'Analysis'}</h3>
              {fire && (
                <span style={{ fontSize: '12px', color: '#888', fontVariantNumeric: 'tabular-nums' }}>
                  {formatAcres(fire.acres)} acres
                </span>
              )}
            </div>

            {/* Layer Toggle Control */}
            <div style={{ display: 'flex', backgroundColor: '#000', borderRadius: '6px', padding: '4px', marginBottom: '22px' }}>
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

            <div style={{ marginBottom: '22px' }}>
              <span style={EYEBROW}>High severity</span>
              <div style={{ fontSize: '30px', fontWeight: 'bold', color: '#fff', marginTop: '4px', lineHeight: 1.1 }}>
                {formatAcres(mapData.metrics.high_severity_acres)}
                <span style={{ fontSize: '15px', fontWeight: 'normal', color: '#888', marginLeft: '6px' }}>acres</span>
              </div>
              <div style={{ fontSize: '12px', color: '#aaa', marginTop: '4px' }}>
                {formatPct(mapData.metrics.high_severity_pct_of_area)}% of the fire · dNBR ≥ 0.66
              </div>
            </div>

            <SeverityBreakdown severity={mapData.severity} />
            <Warnings warnings={mapData.warnings} />
            <LandCoverPanel landcover={mapData.landcover} />
            <QaPanel qa={mapData.qa} />
            <TerrainBars metrics={mapData.metrics} />

            {fire && (
              <p style={{ margin: 0, fontSize: '11px', color: '#777', lineHeight: 1.4 }}>
                Perimeter:{' '}
                <a
                  href={fire.source_url}
                  target="_blank"
                  rel="noreferrer"
                  title={fire.source}
                  style={{ color: '#9ab' }}
                >
                  CAL FIRE FRAP
                </a>
                {' '}· retrieved {fire.retrieved}
              </p>
            )}
          </div>
        )}
      </div>

      <Map
        ref={mapRef}
        initialViewState={FALLBACK_VIEW}
        onLoad={() => setMapLoaded(true)}
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
