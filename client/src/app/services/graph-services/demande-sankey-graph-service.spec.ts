import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { DemandeSankeyGraphService } from './demande-sankey-graph-service';
import { Scenario } from '@app/models/scenario';
import { Weather } from '@app/models/weather';
import { Consumption } from '@app/models/consumption';

const MOCK_SCENARIO: Scenario = {
  id: 1,
  nom: 'Test 2035',
  description: '',
  date_de_debut: '2035-01-01T00:00:00',
  date_de_fin: '2035-12-31T00:00:00',
  pas_de_temps: 'PT1H',
  weather: Weather.Typical,
  consomation: Consumption.Normal,
};

const MOCK_SCENARIO_2: Scenario = { ...MOCK_SCENARIO, id: 2, nom: 'Test 2050' };

const MOCK_SANKEY_RESPONSE = {
  sector: { 0: 'Résidentiel', 1: 'MediumOffice', 2: 'AUTRES' },
  total_electricity: { 0: 10_000_000, 1: 5_000_000, 2: 2_000_000 },
  total_gaz: { 0: 1_000_000, 1: 500_000, 2: 0 },
};

const SANKEY_ENDPOINT = '/api/demande/sankey?CUID=1';

describe('DemandeSankeyGraphService', () => {
  let service: DemandeSankeyGraphService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        DemandeSankeyGraphService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });

    service = TestBed.inject(DemandeSankeyGraphService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    vi.clearAllMocks();
  });

  describe('getStepName', () => {
    it('should return a descriptive step name', () => {
      expect(service.getStepName()).toBeTruthy();
      expect(typeof service.getStepName()).toBe('string');
    });
  });

  describe('generate', () => {
    it('should POST to the sankey endpoint with the scenario', async () => {
      const generatePromise = service.generate(MOCK_SCENARIO);

      const req = httpMock.expectOne(SANKEY_ENDPOINT);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(MOCK_SCENARIO);
      req.flush(MOCK_SANKEY_RESPONSE);

      await generatePromise;
    });

    it('should populate demandNodes after generate completes', async () => {
      const generatePromise = service.generate(MOCK_SCENARIO);
      httpMock.expectOne(SANKEY_ENDPOINT).flush(MOCK_SANKEY_RESPONSE);
      await generatePromise;

      expect(service.demandNodes()).not.toBeNull();
      expect(service.demandNodes()!.length).toBeGreaterThan(0);
    });

    it('should set tempShouldShowSignal to true after generate', async () => {
      const generatePromise = service.generate(MOCK_SCENARIO);
      httpMock.expectOne(SANKEY_ENDPOINT).flush(MOCK_SANKEY_RESPONSE);
      await generatePromise;

      expect(service.tempShouldShowSignal()).toBe(true);
    });

    it('should use cached data when called again with the same scenario', async () => {
      const firstCall = service.generate(MOCK_SCENARIO);
      httpMock.expectOne(SANKEY_ENDPOINT).flush(MOCK_SANKEY_RESPONSE);
      await firstCall;

      const secondCall = service.generate(MOCK_SCENARIO);
      httpMock.expectNone(SANKEY_ENDPOINT);
      await secondCall;
    });

    it('should make a new HTTP request when scenario id changes', async () => {
      const firstCall = service.generate(MOCK_SCENARIO);
      httpMock.expectOne(SANKEY_ENDPOINT).flush(MOCK_SANKEY_RESPONSE);
      await firstCall;

      const secondCall = service.generate(MOCK_SCENARIO_2);
      httpMock.expectOne(SANKEY_ENDPOINT).flush(MOCK_SANKEY_RESPONSE);
      await secondCall;
    });

    it('should produce demand nodes with Résidentiel, Commercial, Industrie, and Autres categories', async () => {
      const generatePromise = service.generate(MOCK_SCENARIO);
      httpMock.expectOne(SANKEY_ENDPOINT).flush(MOCK_SANKEY_RESPONSE);
      await generatePromise;

      const nodeIds = service.demandNodes()!.map(n => n.id);
      expect(nodeIds).toContain('residentiel');
      expect(nodeIds).toContain('commercial');
      expect(nodeIds).toContain('industrie');
      expect(nodeIds).toContain('autres');
    });
  });
});
