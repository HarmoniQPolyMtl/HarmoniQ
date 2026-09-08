vi.mock('plotly.js-dist-min', () => ({
    newPlot: vi.fn(),
    purge: vi.fn(),
    downloadImage: vi.fn(),
    register: vi.fn(),
    setPlotConfig: vi.fn(),
    default: {
        newPlot: vi.fn(),
        purge: vi.fn(),
        downloadImage: vi.fn(),
        register: vi.fn(),
        setPlotConfig: vi.fn(),
    },
}));

vi.mock('leaflet', () => ({
    default: {
        icon: vi.fn().mockReturnValue({}),
        map: vi.fn().mockReturnValue({}),
        marker: vi.fn().mockReturnValue({ addTo: vi.fn(), setIcon: vi.fn(), on: vi.fn() }),
        circleMarker: vi.fn().mockReturnValue({ addTo: vi.fn(), setStyle: vi.fn(), bindPopup: vi.fn().mockReturnThis() }),
        polyline: vi.fn().mockReturnValue({ addTo: vi.fn(), setStyle: vi.fn(), bindPopup: vi.fn().mockReturnThis() }),
        divIcon: vi.fn().mockReturnValue({ options: {} }),
        point: vi.fn((x: number, y: number) => ({ x, y })),
    },
    icon: vi.fn().mockReturnValue({}),
    map: vi.fn().mockReturnValue({}),
    marker: vi.fn().mockReturnValue({ addTo: vi.fn(), setIcon: vi.fn(), on: vi.fn() }),
    circleMarker: vi.fn().mockReturnValue({ addTo: vi.fn(), setStyle: vi.fn(), bindPopup: vi.fn().mockReturnThis() }),
    polyline: vi.fn().mockReturnValue({ addTo: vi.fn(), setStyle: vi.fn(), bindPopup: vi.fn().mockReturnThis() }),
    divIcon: vi.fn().mockReturnValue({ options: {} }),
    point: vi.fn((x: number, y: number) => ({ x, y })),
}));

import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { SimulationTemporalGraphService } from './simulation-temporal-graph-service';
import { ScenariosService } from '../scenarios-service';
import { InfrastruturesService } from '../infrastrutures-service';
import { GraphService } from '@app/services/graph-service';
import { Scenario } from '@app/models/scenario';
import { Weather } from '@app/models/weather';
import { Consumption } from '@app/models/consumption';
import * as _Plotly from 'plotly.js-dist-min';
const Plotly = vi.mocked(_Plotly);

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

const MOCK_SIMULATION_RESPONSE = {
    production: [
        {
            snapshot: '2035-01-01T00:00:00',
            totale: 5000,
            total_eolien: 1000,
            total_solaire: 500,
            total_hydro_fil: 2000,
            total_hydro_reservoir: 1000,
            total_nucleaire: 0,
            total_thermique: 0,
            total_import: 500,
        },
    ],
};

const MOCK_DEMANDE_RESPONSE = {
    total_electricity: { '2035-01-01T00:00:00': 4_800_000 },
};

const RESEAU_ENDPOINT = '/api/reseau/production?is_journalier=false';
const DEMANDE_ENDPOINT = '/api/demande/temporal';

const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe('SimulationTemporalGraphService', () => {
    let service: SimulationTemporalGraphService;
    let httpMock: HttpTestingController;
    let mockGraphService: Partial<GraphService>;
    let mockScenariosService: Partial<ScenariosService>;
    let mockInfrastruturesService: Partial<InfrastruturesService>;

    beforeEach(() => {
        // Clean up any leftover element from prior tests (non-isolated mode)
        document.getElementById('temporal-simulation-id')?.remove();
        const el = document.createElement('div');
        el.id = 'temporal-simulation-id';
        document.body.appendChild(el);

        mockGraphService = {
            aggregateData: vi.fn().mockReturnValue({ x: [], y: [] }),
            hexToRgba: vi.fn().mockReturnValue('rgba(0,0,0,0.7)'),
            getStandardTrace: vi.fn().mockReturnValue({
                x: [],
                y: [],
                type: 'scatter',
                line: { shape: 'spline', color: '#000', width: 4 },
                fill: 'tozeroy',
                fillcolor: 'rgba(0,0,0,0.1)',
                hovertemplate: '',
            }),
            getStandardLayout: vi.fn().mockReturnValue({}),
        };

        mockScenariosService = {
            selectedScenario: vi.fn().mockReturnValue(MOCK_SCENARIO) as any,
        };

        mockInfrastruturesService = {
            buildSimulationPayload: vi
                .fn()
                .mockReturnValue({ nom: 'Test Group', parc_eoliens: [] }),
        };

        TestBed.configureTestingModule({
            providers: [
                SimulationTemporalGraphService,
                { provide: ScenariosService, useValue: mockScenariosService },
                { provide: InfrastruturesService, useValue: mockInfrastruturesService },
                { provide: GraphService, useValue: mockGraphService },
                provideHttpClient(),
                provideHttpClientTesting(),
            ],
        });

        service = TestBed.inject(SimulationTemporalGraphService);
        httpMock = TestBed.inject(HttpTestingController);

        if (!document.getElementById('temporal-simulation-id')) {
            const el2 = document.createElement('div');
            el2.id = 'temporal-simulation-id';
            document.body.appendChild(el2);
        }
    });

    afterEach(() => {
        try {
            httpMock.verify();
        } finally {
            vi.clearAllMocks();
            document.getElementById('temporal-simulation-id')?.remove();
        }
    });

    describe('getStepName', () => {
        it('should return a non-empty string', () => {
            expect(service.getStepName()).toBeTruthy();
        });
    });

    describe('generate', () => {
        it('should POST to both the réseau production and demande temporal endpoints', async () => {
            const generatePromise = service.generate(MOCK_SCENARIO);

            httpMock.expectOne(DEMANDE_ENDPOINT).flush(MOCK_DEMANDE_RESPONSE);
            await tick();
            httpMock.expectOne(RESEAU_ENDPOINT).flush(MOCK_SIMULATION_RESPONSE);

            await generatePromise;
        });

        it('should store the simulation result in cachedSimulationResult', async () => {
            const generatePromise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(DEMANDE_ENDPOINT).flush(MOCK_DEMANDE_RESPONSE);
            await tick();
            httpMock.expectOne(RESEAU_ENDPOINT).flush(MOCK_SIMULATION_RESPONSE);
            await generatePromise;

            expect(service.getCachedSimulationResult()).toEqual(MOCK_SIMULATION_RESPONSE);
        });

        it('should store the demande result in cachedDemandeResult', async () => {
            const generatePromise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(DEMANDE_ENDPOINT).flush(MOCK_DEMANDE_RESPONSE);
            await tick();
            httpMock.expectOne(RESEAU_ENDPOINT).flush(MOCK_SIMULATION_RESPONSE);
            await generatePromise;

            expect(service.getCachedDemandeResult()).toEqual(MOCK_DEMANDE_RESPONSE);
        });

        it('should use cached data for the same scenario on repeated calls', async () => {
            const first = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(DEMANDE_ENDPOINT).flush(MOCK_DEMANDE_RESPONSE);
            await tick();
            httpMock.expectOne(RESEAU_ENDPOINT).flush(MOCK_SIMULATION_RESPONSE);
            await first;

            const second = service.generate(MOCK_SCENARIO);
            httpMock.expectNone(DEMANDE_ENDPOINT);
            await second;
        });

        it('should make new HTTP requests when scenario id changes', async () => {
            const first = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(DEMANDE_ENDPOINT).flush(MOCK_DEMANDE_RESPONSE);
            await tick();
            httpMock.expectOne(RESEAU_ENDPOINT).flush(MOCK_SIMULATION_RESPONSE);
            await first;

            const second = service.generate(MOCK_SCENARIO_2);
            httpMock.expectOne(DEMANDE_ENDPOINT).flush(MOCK_DEMANDE_RESPONSE);
            await tick();
            httpMock.expectOne(RESEAU_ENDPOINT).flush(MOCK_SIMULATION_RESPONSE);
            await second;
        });
    });

    describe('getProductionNodes', () => {
        it('should return an empty array when no cached data exists', () => {
            expect(service.getProductionNodes()).toEqual([]);
        });

        it('should return production nodes with averaged values from cached data', async () => {
            const generatePromise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(DEMANDE_ENDPOINT).flush(MOCK_DEMANDE_RESPONSE);
            await tick();
            httpMock.expectOne(RESEAU_ENDPOINT).flush(MOCK_SIMULATION_RESPONSE);
            await generatePromise;

            const nodes = service.getProductionNodes();
            expect(nodes.length).toBeGreaterThan(0);
            expect(nodes.find((n) => n.id === 'hydro_fil' || n.id === 'hydro_res')).toBeDefined();
        });
    });

    describe('handleData', () => {
        it('should return early when DOM element does not exist', () => {
            document.getElementById('temporal-simulation-id')?.remove();
            expect(() => service.handleData(MOCK_SIMULATION_RESPONSE, MOCK_DEMANDE_RESPONSE)).not.toThrow();
            expect(Plotly.newPlot).not.toHaveBeenCalled();
        });

        it('should call Plotly.newPlot when DOM element exists', () => {
            service.handleData(MOCK_SIMULATION_RESPONSE, MOCK_DEMANDE_RESPONSE);
            expect(Plotly.newPlot).toHaveBeenCalledWith('temporal-simulation-id', expect.any(Array), expect.anything(), expect.anything());
        });

        it('should set totalDemandEnergyTWh signal after calling handleData', () => {
            service.handleData(MOCK_SIMULATION_RESPONSE, MOCK_DEMANDE_RESPONSE);
            expect(service.totalDemandEnergyTWh()).not.toBeNull();
        });

        it('should set energySummaryTWh signal after calling handleData', () => {
            service.handleData(MOCK_SIMULATION_RESPONSE, MOCK_DEMANDE_RESPONSE);
            const summary = service.energySummaryTWh();
            expect(summary).not.toBeNull();
            expect(summary).toHaveProperty('demand');
            expect(summary).toHaveProperty('hydro');
            expect(summary).toHaveProperty('wind');
        });

        it('should pass aggregated data for non-original granularity', () => {
            service.handleData(MOCK_SIMULATION_RESPONSE, MOCK_DEMANDE_RESPONSE, 'weekly');
            expect(mockGraphService.aggregateData).toHaveBeenCalled();
        });

        it('should not aggregate data for original granularity', () => {
            service.handleData(MOCK_SIMULATION_RESPONSE, MOCK_DEMANDE_RESPONSE, 'original');
            expect(mockGraphService.aggregateData).not.toHaveBeenCalled();
        });
    });

    describe('renderDemandPreview', () => {
        it('should return early when DOM element does not exist', () => {
            document.getElementById('temporal-simulation-id')?.remove();
            expect(() => service.renderDemandPreview(MOCK_DEMANDE_RESPONSE)).not.toThrow();
            expect(Plotly.newPlot).not.toHaveBeenCalled();
        });

        it('should call Plotly.newPlot when DOM element exists', () => {
            service.renderDemandPreview(MOCK_DEMANDE_RESPONSE);
            expect(Plotly.newPlot).toHaveBeenCalled();
        });

        it('should aggregate data for non-original granularity', () => {
            service.renderDemandPreview(MOCK_DEMANDE_RESPONSE, 'weekly');
            expect(mockGraphService.aggregateData).toHaveBeenCalled();
        });

        it('should not aggregate for original granularity', () => {
            service.renderDemandPreview(MOCK_DEMANDE_RESPONSE, 'original');
            expect(mockGraphService.aggregateData).not.toHaveBeenCalled();
        });
    });

    describe('clear', () => {
        it('should call Plotly.purge', () => {
            service.clear();
            expect(Plotly.purge).toHaveBeenCalledWith('temporal-simulation-id');
        });
    });
});
