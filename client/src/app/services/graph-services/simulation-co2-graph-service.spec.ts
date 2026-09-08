vi.mock('plotly.js-dist-min', () => ({
    newPlot: vi.fn(),
    purge: vi.fn(),
    restyle: vi.fn(),
    register: vi.fn(),
    setPlotConfig: vi.fn(),
    downloadImage: vi.fn(),
    default: {
        newPlot: vi.fn(),
        purge: vi.fn(),
        restyle: vi.fn(),
        register: vi.fn(),
        setPlotConfig: vi.fn(),
        downloadImage: vi.fn(),
    },
}));

vi.mock('leaflet', () => ({
    default: {
        icon: vi.fn().mockReturnValue({}),
        map: vi.fn().mockReturnValue({}),
        circleMarker: vi.fn().mockReturnValue({ bindPopup: vi.fn().mockReturnThis(), addTo: vi.fn().mockReturnThis(), setStyle: vi.fn().mockReturnThis() }),
        polyline: vi.fn().mockReturnValue({ bindPopup: vi.fn().mockReturnThis(), addTo: vi.fn().mockReturnThis(), setStyle: vi.fn().mockReturnThis() }),
        divIcon: vi.fn().mockReturnValue({ options: {} }),
        point: vi.fn((x: number, y: number) => ({ x, y })),
    },
    icon: vi.fn().mockReturnValue({}),
    map: vi.fn().mockReturnValue({}),
    circleMarker: vi.fn().mockReturnValue({ bindPopup: vi.fn().mockReturnThis(), addTo: vi.fn().mockReturnThis(), setStyle: vi.fn().mockReturnThis() }),
    polyline: vi.fn().mockReturnValue({ bindPopup: vi.fn().mockReturnThis(), addTo: vi.fn().mockReturnThis(), setStyle: vi.fn().mockReturnThis() }),
    divIcon: vi.fn().mockReturnValue({ options: {} }),
    point: vi.fn((x: number, y: number) => ({ x, y })),
}));

import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { SimulationCo2GraphService } from './simulation-co2-graph-service';
import { InfrastruturesService } from '../infrastrutures-service';
import { Scenario } from '@app/models/scenario';
import { Weather } from '@app/models/weather';
import { Consumption } from '@app/models/consumption';
import * as Plotly from 'plotly.js-dist-min';

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

const MOCK_SCENARIO_2: Scenario = { ...MOCK_SCENARIO, id: 2 };

const MOCK_EMISSION_RESPONSE = {
    eolienneparc: [{ id: 1, co2_construction: 100, co2_annuel: 10 }],
    solaire: [{ id: 2, co2_construction: 200, co2_annuel: 20 }],
    hydro: [
        { id: 3, co2_construction: 300, co2_annuel: 30, type_barrage: "Fil de l'eau" },
        { id: 4, co2_construction: 400, co2_annuel: 40, type_barrage: 'Réservoir' },
    ],
    nucleaire: [],
    thermique: [],
    import: [],
};

const EMISSION_ENDPOINT = '/api/reseau/emission';

const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe('SimulationCo2GraphService', () => {
    let service: SimulationCo2GraphService;
    let httpMock: HttpTestingController;
    let mockInfrastruturesService: Partial<InfrastruturesService>;
    let graphDiv: HTMLElement;

    beforeEach(() => {
        graphDiv = document.createElement('div');
        graphDiv.id = 'co2-simulation-id';
        (graphDiv as any).on = vi.fn();
        document.body.appendChild(graphDiv);

        mockInfrastruturesService = {
            buildSimulationPayload: vi.fn().mockReturnValue({ nom: 'Test Group', parc_eoliens: [] }),
        };

        TestBed.configureTestingModule({
            providers: [
                SimulationCo2GraphService,
                { provide: InfrastruturesService, useValue: mockInfrastruturesService },
                provideHttpClient(),
                provideHttpClientTesting(),
            ],
        });

        service = TestBed.inject(SimulationCo2GraphService);
        httpMock = TestBed.inject(HttpTestingController);
    });

    afterEach(() => {
        httpMock.verify();
        vi.clearAllMocks();
        document.getElementById('co2-simulation-id')?.remove();
        document.querySelectorAll('.donut-custom-legend').forEach((el) => el.remove());
    });

    describe('getStepName', () => {
        it('should return a non-empty string', () => {
            expect(service.getStepName()).toBeTruthy();
            expect(typeof service.getStepName()).toBe('string');
        });
    });

    describe('initial state', () => {
        it('should start with isLoading true', () => {
            expect(service.isLoading()).toBe(true);
        });

        it('should start with costMode construction', () => {
            expect(service.costMode).toBe('construction');
        });

        it('should start with no cached data', () => {
            expect(service.cachedData).toBeUndefined();
            expect(service.cachedScenarioId).toBeUndefined();
        });
    });

    describe('generate', () => {
        it('should POST to the emission endpoint with scenario and infra payload', async () => {
            const promise = service.generate(MOCK_SCENARIO);

            const req = httpMock.expectOne(EMISSION_ENDPOINT);
            expect(req.request.method).toBe('POST');
            expect(req.request.body.scenario).toEqual(MOCK_SCENARIO);
            req.flush(MOCK_EMISSION_RESPONSE);

            await tick();
            await promise;
        });

        it('should cache the result and not re-fetch for the same scenario id', async () => {
            const p1 = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(EMISSION_ENDPOINT).flush(MOCK_EMISSION_RESPONSE);
            await tick();
            await p1;

            const p2 = service.generate(MOCK_SCENARIO);
            httpMock.expectNone(EMISSION_ENDPOINT);
            await tick();
            await p2;

            expect(service.cachedScenarioId).toBe(MOCK_SCENARIO.id);
        });

        it('should re-fetch when scenario id changes', async () => {
            const p1 = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(EMISSION_ENDPOINT).flush(MOCK_EMISSION_RESPONSE);
            await tick();
            await p1;

            const p2 = service.generate(MOCK_SCENARIO_2);
            httpMock.expectOne(EMISSION_ENDPOINT).flush(MOCK_EMISSION_RESPONSE);
            await tick();
            await p2;

            expect(service.cachedScenarioId).toBe(MOCK_SCENARIO_2.id);
        });

        it('should set isLoading to false after generating', async () => {
            const promise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(EMISSION_ENDPOINT).flush(MOCK_EMISSION_RESPONSE);
            await tick();
            await promise;

            expect(service.isLoading()).toBe(false);
        });
    });

    describe('getAnnualCo2ByCarrier', () => {
        it('should return empty object when no cached data', () => {
            expect(service.getAnnualCo2ByCarrier()).toEqual({});
        });

        it('should return co2_annuel sums per carrier after data is loaded', async () => {
            const promise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(EMISSION_ENDPOINT).flush(MOCK_EMISSION_RESPONSE);
            await tick();
            await promise;

            const result = service.getAnnualCo2ByCarrier();
            expect(result['eolienneparc']).toBe(10);
            expect(result['solaire']).toBe(20);
            expect(result['hydro_fil']).toBe(30);
            expect(result['hydro_res']).toBe(40);
        });

        it('should split hydro by type_barrage', async () => {
            const promise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(EMISSION_ENDPOINT).flush(MOCK_EMISSION_RESPONSE);
            await tick();
            await promise;

            const result = service.getAnnualCo2ByCarrier();
            expect(result['hydro_fil']).toBeGreaterThan(0);
            expect(result['hydro_res']).toBeGreaterThan(0);
        });
    });

    describe('setCostMode', () => {
        it('should update costMode when mode changes', () => {
            service.setCostMode('annuel');
            expect(service.costMode).toBe('annuel');
        });

        it('should not re-render when mode is already set', () => {
            service.costMode = 'construction';
            service.setCostMode('construction');
            expect(Plotly.newPlot).not.toHaveBeenCalled();
        });

    });
});
