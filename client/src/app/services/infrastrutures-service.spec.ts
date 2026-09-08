vi.mock('leaflet', () => ({
  default: {
    icon: vi.fn().mockReturnValue({}),
    map: vi.fn().mockReturnValue({}),
    marker: vi.fn().mockReturnValue({ addTo: vi.fn(), setIcon: vi.fn(), on: vi.fn(), off: vi.fn(), remove: vi.fn() }),
    markerClusterGroup: vi.fn().mockReturnValue({ addLayer: vi.fn(), addTo: vi.fn() }),
    tileLayer: vi.fn().mockReturnValue({ addTo: vi.fn() }),
    circleMarker: vi.fn().mockReturnValue({ addTo: vi.fn(), bindPopup: vi.fn().mockReturnThis(), setStyle: vi.fn() }),
    polyline: vi.fn().mockReturnValue({ addTo: vi.fn(), bindPopup: vi.fn().mockReturnThis(), setStyle: vi.fn() }),
    popup: vi.fn().mockReturnValue({ setLatLng: vi.fn().mockReturnThis(), setContent: vi.fn().mockReturnThis(), openOn: vi.fn() }),
    Point: vi.fn().mockImplementation((x, y) => ({ x, y, add: vi.fn(), scaleBy: vi.fn() })),
    tileLayer_wms: vi.fn().mockReturnValue({ addTo: vi.fn() }),
  },
  icon: vi.fn().mockReturnValue({}),
  map: vi.fn().mockReturnValue({}),
  marker: vi.fn().mockReturnValue({ addTo: vi.fn(), setIcon: vi.fn(), on: vi.fn(), off: vi.fn(), remove: vi.fn() }),
  markerClusterGroup: vi.fn().mockReturnValue({ addLayer: vi.fn(), addTo: vi.fn() }),
  tileLayer: vi.fn().mockReturnValue({ addTo: vi.fn() }),
  circleMarker: vi.fn().mockReturnValue({ addTo: vi.fn(), bindPopup: vi.fn().mockReturnThis(), setStyle: vi.fn() }),
  polyline: vi.fn().mockReturnValue({ addTo: vi.fn(), bindPopup: vi.fn().mockReturnThis(), setStyle: vi.fn() }),
  popup: vi.fn().mockReturnValue({ setLatLng: vi.fn().mockReturnThis(), setContent: vi.fn().mockReturnThis(), openOn: vi.fn() }),
  Point: vi.fn().mockImplementation((x, y) => ({ x, y, add: vi.fn(), scaleBy: vi.fn() })),
  tileLayer_wms: vi.fn().mockReturnValue({ addTo: vi.fn() }),
}));

import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { InfrastruturesService } from './infrastrutures-service';
import { OpenApiService } from './open-api-service';
import { LocalStorageService } from './local-storage-service';
import { NgbModal } from '@ng-bootstrap/ng-bootstrap';
import { DEFAULT_INFRA_GROUP_ID, InfrastructureGroup } from '@app/models/infrastructure-group';

const INFRA_TYPES = ['hydro', 'eolienneparc', 'solaire', 'thermique', 'nucleaire'];
const API_BASE = '/api';

const MOCK_INFRA_GROUP: InfrastructureGroup = {
  id: 100,
  nom: 'Groupe Test',
  parc_eoliens: ['1'],
  parc_solaires: [],
  central_hydroelectriques: ['2'],
  central_thermique: [],
  central_nucleaire: [],
};

describe('InfrastruturesService', () => {
  let service: InfrastruturesService;
  let httpMock: HttpTestingController;
  let mockOpenApiService: Partial<OpenApiService>;
  let mockStorageService: Partial<LocalStorageService>;
  let mockModalService: Partial<NgbModal>;

  const flushInitialHttpRequests = () => {
    INFRA_TYPES.forEach(type => {
      httpMock.expectOne(`${API_BASE}/${type}`).flush([]);
    });
  };

  beforeEach(() => {
    mockOpenApiService = { getOpenApiSchemas: vi.fn().mockReturnValue({}) };
    mockStorageService = {
      loadElements: vi.fn().mockReturnValue([]),
      loadObject: vi.fn().mockReturnValue(null),
      createElement: vi.fn().mockImplementation((_key: string, el: any) => ({ ...el, id: 100 })),
      updateElement: vi.fn(),
      deleteElement: vi.fn(),
      saveObject: vi.fn(),
    };
    mockModalService = {
      open: vi.fn().mockReturnValue({
        componentInstance: {},
        result: Promise.resolve(null),
      }),
    };

    TestBed.configureTestingModule({
      providers: [
        InfrastruturesService,
        { provide: OpenApiService, useValue: mockOpenApiService },
        { provide: LocalStorageService, useValue: mockStorageService },
        { provide: NgbModal, useValue: mockModalService },
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });

    service = TestBed.inject(InfrastruturesService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    vi.clearAllMocks();
  });

  describe('constructor', () => {
    it('should make HTTP GET requests for all 5 infrastructure types on init', () => {
      INFRA_TYPES.forEach(type => {
        const req = httpMock.expectOne(`${API_BASE}/${type}`);
        expect(req.request.method).toBe('GET');
        req.flush([]);
      });
    });

    it('should load infrastructure groups from storage on init', () => {
      flushInitialHttpRequests();

      expect(mockStorageService.loadElements).toHaveBeenCalledWith('harmoniq_local_infra_groups');
    });
  });

  describe('getInfrasSignalByType', () => {
    it('should return a signal for a valid infra type', () => {
      flushInitialHttpRequests();

      const result = service.getInfrasSignalByType('hydro');
      expect(result).toBeDefined();
      expect(typeof result).toBe('function');
    });

    it('should return an empty signal for an unknown type', () => {
      flushInitialHttpRequests();

      const result = service.getInfrasSignalByType('unknown');
      expect(result()).toEqual([]);
    });
  });

  describe('isInfraSelected', () => {
    it('should return false when no infrastructure group is selected', () => {
      flushInitialHttpRequests();

      expect(service.isInfraSelected('hydro', '1')).toBe(false);
    });

    it('should return true when infra id is in the selected group', () => {
      flushInitialHttpRequests();
      service.selectedInfraGroup.set(MOCK_INFRA_GROUP);

      expect(service.isInfraSelected('eolienneparc', '1')).toBe(true);
    });

    it('should return false when infra id is not in the selected group', () => {
      flushInitialHttpRequests();
      service.selectedInfraGroup.set(MOCK_INFRA_GROUP);

      expect(service.isInfraSelected('eolienneparc', '999')).toBe(false);
    });
  });

  describe('toggleInfra', () => {
    it('should add infra to the group when not selected', () => {
      flushInitialHttpRequests();
      service.selectedInfraGroup.set({ ...MOCK_INFRA_GROUP, parc_eoliens: [] });

      service.toggleInfra('eolienneparc', '5');

      expect(service.selectedInfraGroup()?.parc_eoliens).toContain('5');
    });

    it('should remove infra from the group when already selected', () => {
      flushInitialHttpRequests();
      service.selectedInfraGroup.set({ ...MOCK_INFRA_GROUP, parc_eoliens: ['5'] });

      service.toggleInfra('eolienneparc', '5');

      expect(service.selectedInfraGroup()?.parc_eoliens).not.toContain('5');
    });

    it('should do nothing when no group is selected', () => {
      flushInitialHttpRequests();

      expect(() => service.toggleInfra('eolienneparc', '5')).not.toThrow();
    });

    it('should create a new group when the default Québec group is active', () => {
      flushInitialHttpRequests();
      const def: InfrastructureGroup = {
        id: DEFAULT_INFRA_GROUP_ID,
        nom: 'Infrastructures québécoises',
        parc_eoliens: ['1'],
        parc_solaires: [],
        central_hydroelectriques: [],
        central_thermique: [],
        central_nucleaire: [],
      };
      service.selectedInfraGroup.set(def);

      service.toggleInfra('eolienneparc', '1');

      // It should have called createElement for the new group
      expect(mockStorageService.createElement).toHaveBeenCalledWith(
        'harmoniq_local_infra_groups',
        expect.objectContaining({ nom: "Groupe d'infrastructure 1" }),
      );
      // And the new selected group should have the change
      expect(service.selectedInfraGroup()?.nom).toBe("Groupe d'infrastructure 1");
      expect(service.selectedInfraGroup()?.parc_eoliens).toEqual([]);
    });
  });

  describe('createInfraGroup', () => {
    it('should persist the new group to storage', () => {
      flushInitialHttpRequests();
      const newGroup: InfrastructureGroup = {
        id: 0, nom: 'New Group',
        parc_eoliens: [], parc_solaires: [],
        central_hydroelectriques: [], central_thermique: [], central_nucleaire: [],
      };

      service.createInfraGroup(newGroup);

      expect(mockStorageService.createElement).toHaveBeenCalledWith('harmoniq_local_infra_groups', newGroup);
    });

    it('should set the newly created group as selected', () => {
      flushInitialHttpRequests();
      const newGroup: InfrastructureGroup = {
        id: 0, nom: 'New Group',
        parc_eoliens: [], parc_solaires: [],
        central_hydroelectriques: [], central_thermique: [], central_nucleaire: [],
      };

      service.createInfraGroup(newGroup);

      expect(service.selectedInfraGroup()?.nom).toBe('New Group');
    });
  });

  describe('deleteInfraGroup', () => {
    it('should remove the group from storage and local state', () => {
      flushInitialHttpRequests();
      (mockStorageService.loadElements as ReturnType<typeof vi.fn>).mockReturnValue([MOCK_INFRA_GROUP]);
      service.refreshInfraGroups();

      service.deleteInfraGroup(MOCK_INFRA_GROUP);

      expect(mockStorageService.deleteElement).toHaveBeenCalledWith('harmoniq_local_infra_groups', MOCK_INFRA_GROUP.id);
    });

    it('should set selectedInfraGroup to default when the selected group is deleted', () => {
      flushInitialHttpRequests();
      (mockStorageService.loadElements as ReturnType<typeof vi.fn>).mockReturnValue([MOCK_INFRA_GROUP]);
      service.refreshInfraGroups();
      service.selectedInfraGroup.set(MOCK_INFRA_GROUP);

      service.deleteInfraGroup(MOCK_INFRA_GROUP);

      expect(service.selectedInfraGroup()?.id).toBe(DEFAULT_INFRA_GROUP_ID);
    });
  });

  describe('setInfrasForType', () => {
    it('should create a new group when the default Québec group is selected', () => {
      flushInitialHttpRequests();
      service.selectedInfraGroup.set({
        id: DEFAULT_INFRA_GROUP_ID,
        nom: 'Infrastructures québécoises',
        parc_eoliens: ['1'],
        parc_solaires: [],
        central_hydroelectriques: [],
        central_thermique: [],
        central_nucleaire: [],
      });

      service.setInfrasForType('eolienneparc', []);

      expect(mockStorageService.createElement).toHaveBeenCalledWith(
        'harmoniq_local_infra_groups',
        expect.objectContaining({ nom: "Groupe d'infrastructure 1" }),
      );
    });
  });

  describe('buildSimulationPayload', () => {
    it('should return null when no group is selected', () => {
      flushInitialHttpRequests();
      service.selectedInfraGroup.set(null);

      expect(service.buildSimulationPayload()).toBeNull();
    });

    it('should return a payload with the group nom when a group is selected', () => {
      flushInitialHttpRequests();
      service.selectedInfraGroup.set(MOCK_INFRA_GROUP);

      const payload = service.buildSimulationPayload();

      expect(payload?.nom).toBe(MOCK_INFRA_GROUP.nom);
    });
  });

  describe('getInfraByTypeAndId', () => {
    it('should return undefined when no infra matches', () => {
      INFRA_TYPES.forEach(type => httpMock.expectOne(`${API_BASE}/${type}`).flush([]));
      expect(service.getInfraByTypeAndId('hydro', 999)).toBeUndefined();
    });

    it('should return the infra when it exists', async () => {
      const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));
      INFRA_TYPES.forEach(type => {
        const data = type === 'hydro'
          ? [{ id: 1, nom: 'Barrage Test', type_barrage: 'Réservoir', puissance_nominal: 100, latitude: 50, longitude: -75 }]
          : [];
        httpMock.expectOne(`${API_BASE}/${type}`).flush(data);
      });
      await tick();

      const result = service.getInfraByTypeAndId('hydro', 1);
      expect(result).toBeDefined();
    });
  });

  describe('isNameTaken', () => {
    it('should return false when no infra has that name', () => {
      flushInitialHttpRequests();
      expect(service.isNameTaken('Inexistant')).toBe(false);
    });
  });

  describe('isDefaultInfraGroup', () => {
    it('should return true for the default infra group id', () => {
      flushInitialHttpRequests();
      const group = { id: DEFAULT_INFRA_GROUP_ID, nom: 'Québec', parc_eoliens: [], parc_solaires: [], central_hydroelectriques: [], central_thermique: [], central_nucleaire: [] };
      expect(service.isDefaultInfraGroup(group)).toBe(true);
    });

    it('should return false for a user-created group', () => {
      flushInitialHttpRequests();
      expect(service.isDefaultInfraGroup(MOCK_INFRA_GROUP)).toBe(false);
    });

    it('should return false for null', () => {
      flushInitialHttpRequests();
      expect(service.isDefaultInfraGroup(null)).toBe(false);
    });
  });

  describe('renameInfraGroup', () => {
    it('should update the group name in local state', () => {
      flushInitialHttpRequests();
      (mockStorageService.loadElements as ReturnType<typeof vi.fn>).mockReturnValue([MOCK_INFRA_GROUP]);
      service.refreshInfraGroups();
      service.selectedInfraGroup.set(MOCK_INFRA_GROUP);

      service.renameInfraGroup(MOCK_INFRA_GROUP, 'Nouveau Nom');

      expect(mockStorageService.updateElement).toHaveBeenCalled();
    });

    it('should update selectedInfraGroup when renaming the active group', () => {
      flushInitialHttpRequests();
      (mockStorageService.loadElements as ReturnType<typeof vi.fn>).mockReturnValue([MOCK_INFRA_GROUP]);
      service.refreshInfraGroups();
      service.selectedInfraGroup.set(MOCK_INFRA_GROUP);

      service.renameInfraGroup(MOCK_INFRA_GROUP, 'Nouveau Nom');

      expect(service.selectedInfraGroup()?.nom).toBe('Nouveau Nom');
    });

    it('should not rename the default group', () => {
      flushInitialHttpRequests();
      const defaultGroup = { id: DEFAULT_INFRA_GROUP_ID, nom: 'Québec', parc_eoliens: [], parc_solaires: [], central_hydroelectriques: [], central_thermique: [], central_nucleaire: [] };

      service.renameInfraGroup(defaultGroup, 'Nouveau Nom');

      expect(mockStorageService.updateElement).not.toHaveBeenCalled();
    });

    it('should not rename when name is empty', () => {
      flushInitialHttpRequests();
      service.renameInfraGroup(MOCK_INFRA_GROUP, '   ');
      expect(mockStorageService.updateElement).not.toHaveBeenCalled();
    });
  });

  describe('setInfrasForTypes', () => {
    it('should update infrastructure IDs for specified types', () => {
      flushInitialHttpRequests();
      service.selectedInfraGroup.set(MOCK_INFRA_GROUP);

      service.setInfrasForTypes({ eolienneparc: ['10', '11'] });

      expect(service.selectedInfraGroup()?.parc_eoliens).toEqual(['10', '11']);
    });

    it('should do nothing when no group is selected', () => {
      flushInitialHttpRequests();
      expect(() => service.setInfrasForTypes({ eolienneparc: ['10'] })).not.toThrow();
    });
  });

  describe('refreshService', () => {
    it('should trigger a new HTTP request for the given type', () => {
      flushInitialHttpRequests();

      service.refreshService('hydro');
      httpMock.expectOne(`${API_BASE}/hydro`).flush([]);
    });

    it('should not throw for unknown type', () => {
      flushInitialHttpRequests();
      expect(() => service.refreshService('unknown')).not.toThrow();
    });
  });

  describe('overrideHydroPuissance', () => {
    it('should register an override for a given hydro id', () => {
      flushInitialHttpRequests();

      service.overrideHydroPuissance(42, 500);

      service.selectedInfraGroup.set(MOCK_INFRA_GROUP);
      const payload = service.buildSimulationPayload();
      expect(payload).toBeDefined();
    });
  });

  describe('checkOffshore', () => {
    it('should return true when API says is_offshore', async () => {
      flushInitialHttpRequests();

      const promise = service.checkOffshore(50, -70);
      httpMock.expectOne(req => req.url.includes('offshore-check')).flush({ is_offshore: true });

      const result = await promise;
      expect(result).toBe(true);
    });

    it('should return false when API says not offshore', async () => {
      flushInitialHttpRequests();

      const promise = service.checkOffshore(50, -70);
      httpMock.expectOne(req => req.url.includes('offshore-check')).flush({ is_offshore: false });

      const result = await promise;
      expect(result).toBe(false);
    });

    it('should return false when the API call fails', async () => {
      flushInitialHttpRequests();

      const promise = service.checkOffshore(50, -70);
      httpMock.expectOne(req => req.url.includes('offshore-check')).error(new ErrorEvent('network error'));

      const result = await promise;
      expect(result).toBe(false);
    });
  });

  describe('getAvailableFictionalHydros', () => {
    it('should return an empty array when no hydro container exists', () => {
      flushInitialHttpRequests();
      expect(service.getAvailableFictionalHydros()).toEqual([]);
    });
  });
});
