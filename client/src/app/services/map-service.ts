import { Injectable, NgZone, effect, signal, computed } from '@angular/core';
import * as L from 'leaflet';
import 'leaflet.markercluster';
import { map_icons, prettyNames } from '@app/utils/map-utils';
import { createClusterIcon } from '@app/utils/cluster-icon';
import { InfrastruturesService } from './infrastrutures-service';
import { MapLineService } from './map-line-service';
import { ProtectedAreasService } from './protected-areas-service';
import { InfraDetailService } from './infra-detail-service';

const types = ['hydro', 'eolienneparc', 'solaire', 'thermique', 'nucleaire'];

export interface WindMapCell {
  latitude: number;
  longitude: number;
  mean_wind_kmh: number;
}

export interface WindMapAnnualResponse {
  year: number;
  metric: 'vitesse_vent_kmh_mean';
  cells: WindMapCell[];
  grid: {
    lat_step_deg: number;
    lon_step_deg: number;
    lat_half_step_deg: number;
    lon_half_step_deg: number;
  };
  value_range: {
    min: number;
    max: number;
  };
}

// Water color on the CartoDB light basemap
const WATER_COLOR = { r: 212, g: 218, b: 220 }; // #d4dadc
const WATER_COLOR_TOLERANCE = 12;

// Types that are NOT allowed on water
const WATER_BLOCKED_TYPES: Record<string, string> = {
  'thermique': 'centrales thermiques',
  'solaire': 'parcs solaires',
  'nucleaire': 'centrales nucléaires',
};

@Injectable({
  providedIn: 'root',
})
export class MapService {
  get map() { return this._map; }

  private _map?: L.Map;
  private clusterGroup?: L.MarkerClusterGroup;
  private windLayerGroup?: L.LayerGroup;
  private windLegendControl?: L.Control;
  private windRenderToken = 0;
  private readonly windSubdivisionFactor = 7;
  private readonly windFillOpacity = 0.38;
  private quebecBoundaryGeometry:
    | { type: 'Polygon'; coordinates: number[][][] }
    | { type: 'MultiPolygon'; coordinates: number[][][][] }
    | null
    | undefined;
  private quebecBoundaryLoadPromise?: Promise<void>;

  private markers: any = {
    eolienneparc: {},
    solaire: {},
    thermique: {},
    hydro: {},
    nucleaire: {},
  }

  // Filter Signals
  mapFilterName = signal('');
  mapFilterTypes = signal<Set<string>>(new Set(types)); // Show all by default
  mapFilterMinPower = signal<number | null>(null);
  mapFilterMaxPower = signal<number | null>(null);
  showRealInfra = signal(true);
  showUserInfra = signal(true);

  hasSelection = computed(() => this.mapFilterTypes().size > 0 && (this.showRealInfra() || this.showUserInfra()));
  private lastTypeSelection: Set<string> = new Set(types);

  private previousSelectedType: string | null = null;
  private previousSelectedId: string | null = null;

  constructor(
    private infrasService: InfrastruturesService,
    private mapLineService: MapLineService,
    private protectedAreasService: ProtectedAreasService,
    private infraDetailService: InfraDetailService,
    private ngZone: NgZone
  ) {
    effect(() => {
      // reload markers when selected infra group changes
      infrasService.selectedInfraGroup();
      this.reloadMarkers();
    });

    this.infrasService.infraToggled.subscribe(({ type, id, isActive }: { type: string, id: string, isActive: boolean }) => {
      this.updateMarker(type, id, isActive);
    });

    types.forEach(type => {
      effect(() => {
        this.infrasService.getInfrasSignalByType(type)();
        this.reloadMarkers();
      });
    });

    // Auto-reload markers when any filter changes
    effect(() => {
      this.mapFilterName();
      this.mapFilterTypes();
      this.mapFilterMinPower();
      this.mapFilterMaxPower();
      this.showRealInfra();
      this.showUserInfra();
      this.reloadMarkers();
    });

    // Watch for selected infra changes to highlight the marker in blue
    effect(() => {
      const selected = this.infraDetailService.selectedInfra();

      // Restore previously selected marker to its normal icon
      if (this.previousSelectedType && this.previousSelectedId) {
        const prevMarker = this.markers[this.previousSelectedType]?.[parseInt(this.previousSelectedId)];
        if (prevMarker) {
          const isActive = this.infrasService.isInfraSelected(this.previousSelectedType, this.previousSelectedId);
          const iconName = !isActive ? `${this.previousSelectedType}gris` : this.previousSelectedType;
          prevMarker.setIcon(map_icons[iconName]);
          (prevMarker.options as any).infraActive = isActive;
          if (this.clusterGroup) {
            this.clusterGroup.refreshClusters();
          }
        }
        this.previousSelectedType = null;
        this.previousSelectedId = null;
      }

      // Highlight the newly selected marker in blue
      if (selected) {
        const marker = this.markers[selected.type]?.[parseInt(selected.id)];
        if (marker) {
          marker.setIcon(map_icons[`${selected.type}bleu`]);
          if (this.clusterGroup) {
            this.clusterGroup.refreshClusters();
          }
          this.previousSelectedType = selected.type;
          this.previousSelectedId = selected.id;
        }
      }
    });
  }


  toggleVisibility(): void {
    if (this.hasSelection()) {
      this.lastTypeSelection = new Set(this.mapFilterTypes());
      this.deselectAll();
    } else {
      if (!this.lastTypeSelection || this.lastTypeSelection.size === 0) {
        this.selectAll();
      } else {
        this.mapFilterTypes.set(new Set(this.lastTypeSelection));
      }
    }
    this.reloadMarkers();
  }

  selectAll() {
    this.mapFilterTypes.set(new Set(types));
  }

  deselectAll() {
    this.mapFilterTypes.set(new Set());
  }

  onMapLoaded() { setTimeout(() => this.map?.invalidateSize(), 250); }

  createMap() {
    if (this.map)
      throw new Error('Map already created');

    const map = L.map('map', {
      zoomControl: false,
      attributionControl: false,
      maxZoom: 12,
      minZoom: 5
    }).setView([52.9399, -67], 4);

    // Texture of the map, could be fun to add some more
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
      crossOrigin: 'anonymous',
    } as any).addTo(map);

    var bounds: L.LatLngBoundsExpression = [
      [40.0, -90.0],
      [65.0, -50.0]
    ];
    map.setMaxBounds(bounds);

    map.getContainer().addEventListener("dragover", function (e: any) {
      e.preventDefault();
    });

    const infrasService = this.infrasService;
    const self = this;
    map.getContainer().addEventListener("drop", function (e: any) {
      e.preventDefault();

      const dragData = e.dataTransfer.getData("text/plain");
      if (!dragData || !dragData.includes(',')) {
        return; // Ignore non-infrastructure drags (e.g. text selection, files)
      }

      const [className, type] = dragData.split(",");

      if (!type || !types.includes(type)) {
        return; // Ensure only valid infrastructure types are accepted
      }

      const mapPos = map.getContainer().getBoundingClientRect();
      const x = e.clientX - mapPos.left;
      const y = e.clientY - mapPos.top;

      if (type === 'hydro') {
        return;
      }
      // Check if drop is on water and type is blocked
      const isOnWater = self.isPixelWater(map, x, y);
      const blockedLabel = WATER_BLOCKED_TYPES[type];

      if (isOnWater && blockedLabel) {
        self.showWaterBlockedToast(`Impossible d'ajouter des ${blockedLabel} dans une zone d'eau.`);
        return;
      }
      const latlng = map.containerPointToLatLng([x, y]);


      const lat = parseFloat(latlng.lat.toFixed(6));
      const lng = parseFloat(latlng.lng.toFixed(6));

      infrasService.createInfra(className, type, lat, lng, isOnWater);
    });


    this._map = map;

    const LeafletInstance = (window as any).L || L;
    this.clusterGroup = LeafletInstance.markerClusterGroup({
      maxClusterRadius: 70,
      disableClusteringAtZoom: 8,
      spiderfyOnMaxZoom: true,
      showCoverageOnHover: false,
      iconCreateFunction: (cluster: any) => createClusterIcon(cluster),
    });
    map.addLayer(this.clusterGroup as any);

    return map;
  }

  destroyMap() {
    if (!this.map)
      throw new Error('Map not created');

    this.clearWindLayer();
    this.map.remove();
    this._map = undefined;
    this.clusterGroup = undefined;
  }

  initMarkers() {
    if (!this.map) return;

    const searchTerm = this.mapFilterName().trim().toLowerCase();
    const allowedTypes = this.mapFilterTypes();
    const minPower = this.mapFilterMinPower();
    const maxPower = this.mapFilterMaxPower();

    types.forEach(type => {
      if (!allowedTypes.has(type)) return;

      let infras = this.infrasService.getInfrasSignalByType(type)();

      // Apply Name filter
      if (searchTerm) {
        infras = infras.filter(i => (i.nom || '').toLowerCase().includes(searchTerm));
      }

      // Apply Power filters
      if (minPower !== null || maxPower !== null) {
        infras = infras.filter(i => {
          const p = (i as any).puissance_nominal;
          if (typeof p !== 'number') return true; // fallback if missing
          if (minPower !== null && p < minPower) return false;
          if (maxPower !== null && p > maxPower) return false;
          return true;
        });
      }

      // Apply Origin filters
      const showReal = this.showRealInfra();
      const showUser = this.showUserInfra();
      infras = infras.filter(i => {
        const isUser = (i as any).isUserCreated === true;
        if (isUser && !showUser) return false;
        if (!isUser && !showReal) return false;
        return true;
      });

      this.addMarkers(type, infras);
    });
  }

  destroyMarkers() {
    if (!this.map) return;
    types.forEach(type => this.removeMarkers(type));
  }

  reloadMarkers() {
    this.destroyMarkers();
    this.initMarkers();
  }

  async renderWindHeatmap(data: WindMapAnnualResponse): Promise<void> {
    if (!this.map) return;

    const token = ++this.windRenderToken;
    this.clearWindLayerInternal();
    await this.ensureQuebecBoundaryLoaded();
    if (!this.map || token !== this.windRenderToken) return;

    const group = L.layerGroup().addTo(this.map);
    const subdivisions = this.windSubdivisionFactor;
    const subLatStep = data.grid.lat_step_deg / subdivisions;
    const subLonStep = data.grid.lon_step_deg / subdivisions;
    const subLatHalf = subLatStep / 2.0;
    const subLonHalf = subLonStep / 2.0;
    const min = Number(data.value_range?.min ?? 0);
    const max = Number(data.value_range?.max ?? 0);
    const gridIndex = this.buildWindGridIndex(data.cells);

    data.cells.forEach((cell) => {
      const value = Number(cell.mean_wind_kmh);
      const baseMinLat = Number(cell.latitude) - data.grid.lat_half_step_deg;
      const baseMinLon = Number(cell.longitude) - data.grid.lon_half_step_deg;

      for (let i = 0; i < subdivisions; i++) {
        const centerLat = baseMinLat + subLatHalf + i * subLatStep;
        for (let j = 0; j < subdivisions; j++) {
          const centerLon = baseMinLon + subLonHalf + j * subLonStep;
          if (!this.isInsideQuebecBoundary(centerLat, centerLon)) continue;
          const interpolated = this.interpolateWindValue(centerLat, centerLon, gridIndex, value);
          const fillColor = this.getWindColor(interpolated, min, max);

          const bounds: L.LatLngBoundsExpression = [
            [centerLat - subLatHalf, centerLon - subLonHalf],
            [centerLat + subLatHalf, centerLon + subLonHalf],
          ];

          const rect = L.rectangle(bounds, {
            color: fillColor,
            weight: 0,
            fillColor: fillColor,
            fillOpacity: this.windFillOpacity,
            interactive: false,
          });
          rect.addTo(group);
        }
      }
    });

    this.windLayerGroup = group;
    this.windLegendControl = this.createWindLegend(data.year, min, max);
    this.windLegendControl.addTo(this.map);
  }

  clearWindLayer() {
    this.windRenderToken++;
    this.clearWindLayerInternal();
  }

  private clearWindLayerInternal() {
    if (this.windLegendControl && this.map) {
      this.map.removeControl(this.windLegendControl);
    }
    this.windLegendControl = undefined;

    if (this.windLayerGroup) {
      this.windLayerGroup.clearLayers();
      this.windLayerGroup.remove();
    }
    this.windLayerGroup = undefined;
  }

  private async ensureQuebecBoundaryLoaded(): Promise<void> {
    if (this.quebecBoundaryGeometry !== undefined) return;
    if (this.quebecBoundaryLoadPromise) {
      await this.quebecBoundaryLoadPromise;
      return;
    }

    this.quebecBoundaryLoadPromise = fetch('/quebec-boundary.geojson')
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Failed to load Quebec boundary: HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((geojson: any) => {
        this.quebecBoundaryGeometry = this.extractQuebecBoundaryGeometry(geojson);
      })
      .catch((error) => {
        console.warn('Wind map boundary load failed, rendering without Quebec clip.', error);
        this.quebecBoundaryGeometry = null;
      })
      .finally(() => {
        this.quebecBoundaryLoadPromise = undefined;
      });

    await this.quebecBoundaryLoadPromise;
  }

  private extractQuebecBoundaryGeometry(geojson: any):
    | { type: 'Polygon'; coordinates: number[][][] }
    | { type: 'MultiPolygon'; coordinates: number[][][][] }
    | null {
    if (!geojson || !Array.isArray(geojson.features)) return null;
    const feature = geojson.features.find((f: any) => {
      const rawName = String(f?.properties?.name ?? f?.properties?.NAME ?? '').toLowerCase();
      const normalized = rawName.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
      return normalized === 'quebec';
    });
    const geometry = feature?.geometry;
    if (!geometry || !geometry.type || !geometry.coordinates) return null;
    if (geometry.type === 'Polygon' || geometry.type === 'MultiPolygon') {
      return geometry;
    }
    return null;
  }

  private isInsideQuebecBoundary(latitude: number, longitude: number): boolean {
    if (this.quebecBoundaryGeometry === undefined) return true;
    if (this.quebecBoundaryGeometry === null) return true;

    if (this.quebecBoundaryGeometry.type === 'Polygon') {
      return this.isPointInPolygon(latitude, longitude, this.quebecBoundaryGeometry.coordinates);
    }

    return this.quebecBoundaryGeometry.coordinates.some((polygon) =>
      this.isPointInPolygon(latitude, longitude, polygon),
    );
  }

  private isPointInPolygon(latitude: number, longitude: number, polygon: number[][][]): boolean {
    if (!polygon.length) return false;
    if (!this.isPointInRing(latitude, longitude, polygon[0])) return false;

    for (let i = 1; i < polygon.length; i++) {
      if (this.isPointInRing(latitude, longitude, polygon[i])) {
        return false;
      }
    }
    return true;
  }

  private isPointInRing(latitude: number, longitude: number, ring: number[][]): boolean {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = Number(ring[i][0]);
      const yi = Number(ring[i][1]);
      const xj = Number(ring[j][0]);
      const yj = Number(ring[j][1]);
      const intersects =
        yi > latitude !== yj > latitude &&
        longitude < ((xj - xi) * (latitude - yi)) / ((yj - yi) || 1e-12) + xi;
      if (intersects) {
        inside = !inside;
      }
    }
    return inside;
  }

  private buildWindGridIndex(cells: WindMapCell[]): {
    latitudes: number[];
    longitudes: number[];
    valueByKey: Map<string, number>;
  } {
    const latitudes = Array.from(new Set(cells.map((c) => Number(c.latitude)))).sort((a, b) => a - b);
    const longitudes = Array.from(new Set(cells.map((c) => Number(c.longitude)))).sort((a, b) => a - b);
    const valueByKey = new Map<string, number>();

    cells.forEach((cell) => {
      valueByKey.set(this.windGridKey(Number(cell.latitude), Number(cell.longitude)), Number(cell.mean_wind_kmh));
    });

    return { latitudes, longitudes, valueByKey };
  }

  private windGridKey(latitude: number, longitude: number): string {
    return `${latitude.toFixed(6)}|${longitude.toFixed(6)}`;
  }

  private getWindGridValue(
    grid: { valueByKey: Map<string, number> },
    latitude: number,
    longitude: number,
  ): number | null {
    const value = grid.valueByKey.get(this.windGridKey(latitude, longitude));
    return Number.isFinite(value) ? Number(value) : null;
  }

  private findBracket(values: number[], target: number): [number, number] {
    if (values.length <= 1) return [0, 0];
    if (target <= values[0]) return [0, 0];
    const last = values.length - 1;
    if (target >= values[last]) return [last, last];

    let lo = 0;
    let hi = last;
    while (lo + 1 < hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (values[mid] <= target) {
        lo = mid;
      } else {
        hi = mid;
      }
    }
    return [lo, hi];
  }

  private interpolateWindValue(
    latitude: number,
    longitude: number,
    grid: {
      latitudes: number[];
      longitudes: number[];
      valueByKey: Map<string, number>;
    },
    fallback: number,
  ): number {
    const [lat0Idx, lat1Idx] = this.findBracket(grid.latitudes, latitude);
    const [lon0Idx, lon1Idx] = this.findBracket(grid.longitudes, longitude);

    const lat0 = grid.latitudes[lat0Idx];
    const lat1 = grid.latitudes[lat1Idx];
    const lon0 = grid.longitudes[lon0Idx];
    const lon1 = grid.longitudes[lon1Idx];

    const q11 = this.getWindGridValue(grid, lat0, lon0);
    const q21 = this.getWindGridValue(grid, lat0, lon1);
    const q12 = this.getWindGridValue(grid, lat1, lon0);
    const q22 = this.getWindGridValue(grid, lat1, lon1);

    if (q11 !== null && q21 !== null && q12 !== null && q22 !== null) {
      const tx = lon1 !== lon0 ? (longitude - lon0) / (lon1 - lon0) : 0.0;
      const ty = lat1 !== lat0 ? (latitude - lat0) / (lat1 - lat0) : 0.0;
      const r1 = q11 * (1 - tx) + q21 * tx;
      const r2 = q12 * (1 - tx) + q22 * tx;
      return r1 * (1 - ty) + r2 * ty;
    }

    const candidates: Array<{ value: number; dist: number }> = [];
    const addCandidate = (value: number | null, lat: number, lon: number) => {
      if (value === null) return;
      const dLat = latitude - lat;
      const dLon = longitude - lon;
      candidates.push({ value, dist: Math.hypot(dLat, dLon) });
    };

    addCandidate(q11, lat0, lon0);
    addCandidate(q21, lat0, lon1);
    addCandidate(q12, lat1, lon0);
    addCandidate(q22, lat1, lon1);

    if (!candidates.length) return fallback;
    if (candidates.length === 1) return candidates[0].value;

    let weightedSum = 0;
    let weightTotal = 0;
    candidates.forEach((candidate) => {
      const weight = 1 / Math.max(candidate.dist, 1e-6);
      weightedSum += candidate.value * weight;
      weightTotal += weight;
    });

    return weightTotal > 0 ? weightedSum / weightTotal : fallback;
  }

  private getWindColor(value: number, min: number, max: number): string {
    if (!Number.isFinite(value)) return '#999999';
    const ratio = max > min ? (value - min) / (max - min) : 0.5;
    const clamped = Math.max(0, Math.min(1, ratio));
    const hue = 220 - clamped * 220;
    return `hsl(${hue}, 85%, 48%)`;
  }

  private createWindLegend(year: number, min: number, max: number): L.Control {
    const control = new L.Control({ position: 'bottomleft' });
    control.onAdd = (_map: L.Map) => {
      const div = L.DomUtil.create('div');
      const maxLabel = Number.isFinite(max) ? max.toFixed(1) : '-';
      const minLabel = Number.isFinite(min) ? min.toFixed(1) : '-';
      div.style.background = 'rgba(255,255,255,0.95)';
      div.style.padding = '10px 12px';
      div.style.borderRadius = '8px';
      div.style.boxShadow = '0 2px 8px rgba(0,0,0,0.2)';
      div.style.fontSize = '12px';
      div.style.lineHeight = '1.3';
      div.style.minWidth = '190px';
      div.innerHTML = `
        <div style="font-weight:700; margin-bottom:6px;">Vent moyen ${year}</div>
        <div style="height:10px; border-radius:6px; margin-bottom:6px;
          background: linear-gradient(to right,
          hsl(220, 85%, 48%),
          hsl(160, 85%, 48%),
          hsl(100, 85%, 48%),
          hsl(40, 85%, 48%),
          hsl(0, 85%, 48%));"></div>
        <div style="display:flex; justify-content:space-between;">
          <span>${minLabel} km/h</span>
          <span>${maxLabel} km/h</span>
        </div>
      `;
      return div;
    };
    return control;
  }

  addMarkers(type: string, infras: any[]) {
    infras.forEach(infra => this.addMarker(type, infra));
  }

  removeMarkers(type: string) {
    const markers = this.markers[type];
    for (const marker of Object.values(markers)) {
      const m = marker as L.Marker;
      if (this.clusterGroup) {
        this.clusterGroup.removeLayer(m);
      }
      m.remove();
    }
    this.markers[type] = {};
  }

  addMarker(type: string, data: any) {
    if (!this.map) return;
    const isActive = this.infrasService.isInfraSelected(type, data.id.toString());
    const iconName = !isActive ? `${type}gris` : type;
    const icon = map_icons[iconName];

    const marker = L.marker([data.latitude, data.longitude], {
      icon: icon,
      infraType: type,
      infraActive: isActive,
    } as any);

    // Open detail panel on marker click instead of popup
    marker.on('click', () => {
      this.infraDetailService.openDetail(type, data.id.toString());
    });

    if (this.clusterGroup) {
      this.clusterGroup.addLayer(marker);
    } else {
      marker.addTo(this.map);
    }

    this.markers[type][data.id] = marker;
  }

  showMarker(type: string, id: string) {
    this.infraDetailService.openDetail(type, id);
  }

  flyToInfra(type: string, id: string) {
    if (!this._map) return;
    const marker = this.markers[type]?.[parseInt(id)];
    if (marker) {
      this._map.setView(marker.getLatLng(), 10, { animate: false });
    } else {
      const infra = this.infrasService.getInfraByTypeAndId(type, id);
      if (infra) {
        this._map.setView([infra.latitude, infra.longitude], 10, { animate: false });
      }
    }
  }

  private updateMarker(type: string, id: string, isActive: boolean) {
    let infraId = parseInt(id);
    const marker = this.markers[type][infraId];

    if (!marker) return;
    marker.setIcon(!isActive ? map_icons[`${type}gris`] : map_icons[type]);
    (marker.options as any).infraActive = isActive;

    if (this.clusterGroup) {
      this.clusterGroup.refreshClusters();
    }
  }

  /**
   * Check if a pixel on the map corresponds to water by reading the tile color.
   */
  private isPixelWater(map: L.Map, containerX: number, containerY: number): boolean {
    try {
      const container = map.getContainer();
      const tilePane = container.querySelector('.leaflet-tile-pane') as HTMLElement;
      if (!tilePane) return false;

      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      if (!ctx) return false;

      canvas.width = container.clientWidth;
      canvas.height = container.clientHeight;

      // Get all visible tile images
      const tileImages = tilePane.querySelectorAll('img.leaflet-tile') as NodeListOf<HTMLImageElement>;

      for (const img of Array.from(tileImages)) {
        if (!img.complete || img.naturalWidth === 0) continue;

        // Get the tile's rendered position relative to the container
        const imgRect = img.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();

        const dx = imgRect.left - containerRect.left;
        const dy = imgRect.top - containerRect.top;

        try {
          ctx.drawImage(img, dx, dy, imgRect.width, imgRect.height);
        } catch {
          // CORS or other drawing errors — skip this tile
        }
      }

      const pixel = ctx.getImageData(containerX, containerY, 1, 1).data;
      const [r, g, b] = [pixel[0], pixel[1], pixel[2]];

      const dr = Math.abs(r - WATER_COLOR.r);
      const dg = Math.abs(g - WATER_COLOR.g);
      const db = Math.abs(b - WATER_COLOR.b);

      return dr <= WATER_COLOR_TOLERANCE && dg <= WATER_COLOR_TOLERANCE && db <= WATER_COLOR_TOLERANCE;
    } catch {
      return false;
    }
  }

  /**
   * Show a temporary toast notification on the map.
   */
  private showWaterBlockedToast(message: string): void {
    // Remove any existing toast
    const existing = document.querySelector('.hq-water-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'hq-water-toast';
    toast.innerHTML = `
      <span>${message}</span>
    `;

    document.body.appendChild(toast);

    // trigger enter animation
    requestAnimationFrame(() => {
      toast.classList.add('hq-water-toast--visible');
    });

    setTimeout(() => {
      toast.classList.remove('hq-water-toast--visible');
      toast.classList.add('hq-water-toast--exit');
      toast.addEventListener('transitionend', () => toast.remove());
      // fallback removal
      setTimeout(() => toast.remove(), 600);
    }, 3500);
  }
}
