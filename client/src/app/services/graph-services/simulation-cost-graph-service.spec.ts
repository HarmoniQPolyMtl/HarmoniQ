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
import { SimulationCostGraphService } from './simulation-cost-graph-service';
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

const MOCK_COST_RESPONSE = {
    eolienneparc: [{ id: 1, cout_construction: 1_000_000, cout_annuel: 50_000 }],
    solaire: [{ id: 2, cout_construction: 500_000, cout_annuel: 20_000 }],
    hydro: [
        { id: 3, cout_construction: 2_000_000, cout_annuel: 100_000, type_barrage: "Fil de l'eau" },
        { id: 4, cout_construction: 3_000_000, cout_annuel: 150_000, type_barrage: 'Réservoir' },
    ],
    nucleaire: [],
    thermique: [],
};

const COUT_ENDPOINT = '/api/reseau/cout';

const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe('SimulationCostGraphService', () => {
    let service: SimulationCostGraphService;
    let httpMock: HttpTestingController;
    let mockInfrastruturesService: Partial<InfrastruturesService>;
    let graphDiv: HTMLElement;

    beforeEach(() => {
        graphDiv = document.createElement('div');
        graphDiv.id = 'cost-simulation-id';
        (graphDiv as any).on = vi.fn();
        document.body.appendChild(graphDiv);

        const top10Div = document.createElement('div');
        top10Div.id = 'cost-top10-id';
        document.body.appendChild(top10Div);

        const rentabiliteDiv = document.createElement('div');
        rentabiliteDiv.id = 'cost-rentabilite-id';
        document.body.appendChild(rentabiliteDiv);

        mockInfrastruturesService = {
            buildSimulationPayload: vi.fn().mockReturnValue({ nom: 'Test Group', parc_eoliens: [] }),
            getInfrasSignalByType: vi.fn().mockReturnValue(() => []),
        };

        TestBed.configureTestingModule({
            providers: [
                SimulationCostGraphService,
                { provide: InfrastruturesService, useValue: mockInfrastruturesService },
                provideHttpClient(),
                provideHttpClientTesting(),
            ],
        });

        service = TestBed.inject(SimulationCostGraphService);
        httpMock = TestBed.inject(HttpTestingController);
    });

    afterEach(() => {
        httpMock.verify();
        vi.clearAllMocks();
        document.getElementById('cost-simulation-id')?.remove();
        document.getElementById('cost-top10-id')?.remove();
        document.getElementById('cost-rentabilite-id')?.remove();
        document.querySelectorAll('.donut-custom-legend').forEach((el) => el.remove());
    });

    describe('getStepName', () => {
        it('should return a non-empty string', () => {
            expect(service.getStepName()).toBeTruthy();
        });
    });

    describe('initial state', () => {
        it('should start with isLoading true', () => {
            expect(service.isLoading()).toBe(true);
        });

        it('should start with costMode annuel', () => {
            expect(service.costMode).toBe('annuel');
        });

        it('should start with no cached data', () => {
            expect(service.cachedData).toBeUndefined();
            expect(service.cachedScenarioId).toBeUndefined();
        });
    });

    describe('generate', () => {
        it('should POST to the cout endpoint with scenario payload', async () => {
            const promise = service.generate(MOCK_SCENARIO);
            const req = httpMock.expectOne(COUT_ENDPOINT);
            expect(req.request.method).toBe('POST');
            expect(req.request.body.scenario).toEqual(MOCK_SCENARIO);
            req.flush(MOCK_COST_RESPONSE);
            await tick();
            await promise;
        });

        it('should cache result and not re-fetch for the same scenario', async () => {
            const p1 = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(COUT_ENDPOINT).flush(MOCK_COST_RESPONSE);
            await tick();
            await p1;

            const p2 = service.generate(MOCK_SCENARIO);
            httpMock.expectNone(COUT_ENDPOINT);
            await tick();
            await p2;
        });

        it('should re-fetch when scenario id changes', async () => {
            const p1 = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(COUT_ENDPOINT).flush(MOCK_COST_RESPONSE);
            await tick();
            await p1;

            const p2 = service.generate(MOCK_SCENARIO_2);
            httpMock.expectOne(COUT_ENDPOINT).flush(MOCK_COST_RESPONSE);
            await tick();
            await p2;

            expect(service.cachedScenarioId).toBe(MOCK_SCENARIO_2.id);
        });

        it('should set isLoading to false after generation', async () => {
            const promise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(COUT_ENDPOINT).flush(MOCK_COST_RESPONSE);
            await tick();
            await promise;

            expect(service.isLoading()).toBe(false);
        });

        it('should call Plotly.newPlot for the cost pie chart', async () => {
            const promise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(COUT_ENDPOINT).flush(MOCK_COST_RESPONSE);
            await tick();
            await promise;

            expect(Plotly.newPlot).toHaveBeenCalled();
        });
    });

    describe('setCostMode', () => {
        it('should update costMode when changing to construction', () => {
            service.setCostMode('construction');
            expect(service.costMode).toBe('construction');
        });

        it('should not re-render when mode is unchanged', () => {
            service.costMode = 'annuel';
            service.setCostMode('annuel');
            expect(Plotly.newPlot).not.toHaveBeenCalled();
        });

        it('should re-render cached data when mode changes', async () => {
            const promise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(COUT_ENDPOINT).flush(MOCK_COST_RESPONSE);
            await tick();
            await promise;

            vi.clearAllMocks();
            service.setCostMode('construction');
            expect(Plotly.newPlot).toHaveBeenCalled();
        });
    });

    describe('handleData unit selection', () => {
        it('should use k$ for the default mock data (annuel sums in thousands)', () => {
            service.handleData(MOCK_COST_RESPONSE);
            const callArgs = (Plotly.newPlot as any).mock.calls[0];
            const pieTrace = callArgs[1][0];
            expect(pieTrace.title.text).toContain('k$');
        });

        it('should use M$ for values in millions', () => {
            const largeData = {
                eolienneparc: [{ cout_construction: 50_000_000, cout_annuel: 2_000_000 }],
                solaire: [],
                hydro: [],
                nucleaire: [],
                thermique: [],
            };
            service.handleData(largeData);
            const callArgs = (Plotly.newPlot as any).mock.calls[0];
            const pieTrace = callArgs[1][0];
            expect(pieTrace.title.text).toContain('M$');
        });

        it('should use $ for very small values', () => {
            const tinyData = {
                eolienneparc: [{ cout_construction: 5, cout_annuel: 3 }],
                solaire: [],
                hydro: [],
                nucleaire: [],
                thermique: [],
            };
            service.handleData(tinyData);
            const callArgs = (Plotly.newPlot as any).mock.calls[0];
            const pieTrace = callArgs[1][0];
            expect(pieTrace.title.text).not.toContain('k$');
            expect(pieTrace.title.text).not.toContain('M$');
        });
    });
});
