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
import { DemandeTemporalGraphService } from './demande-temporal-graph-service';
import { ScenariosService } from '../scenarios-service';
import { Scenario } from '@app/models/scenario';
import { Weather } from '@app/models/weather';
import { Consumption } from '@app/models/consumption';

const MOCK_SCENARIO: Scenario = {
    id: 1,
    nom: 'Test',
    description: '',
    date_de_debut: '2035-01-01T00:00:00',
    date_de_fin: '2035-12-31T00:00:00',
    pas_de_temps: 'PT1H',
    weather: Weather.Typical,
    consomation: Consumption.Normal,
};

const MOCK_SCENARIO_2: Scenario = { ...MOCK_SCENARIO, id: 2 };

const MOCK_RESPONSE = {
    total_electricity: {
        '2035-01-01T00:00:00': 4_000_000,
        '2035-01-01T01:00:00': 5_000_000,
    },
};

const ENDPOINT = '/api/demande/temporal';

const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe('DemandeTemporalGraphService', () => {
    let service: DemandeTemporalGraphService;
    let httpMock: HttpTestingController;

    beforeEach(() => {
        TestBed.configureTestingModule({
            providers: [
                DemandeTemporalGraphService,
                { provide: ScenariosService, useValue: {} },
                provideHttpClient(),
                provideHttpClientTesting(),
            ],
        });

        service = TestBed.inject(DemandeTemporalGraphService);
        httpMock = TestBed.inject(HttpTestingController);
    });

    afterEach(() => {
        httpMock.verify();
        vi.clearAllMocks();
    });

    describe('getStepName', () => {
        it('should return a non-empty string', () => {
            expect(service.getStepName()).toBeTruthy();
        });
    });

    describe('initial state', () => {
        it('should have peakDemandMW as null', () => {
            expect(service.peakDemandMW()).toBeNull();
        });

        it('should have totalDemandEnergyTWh as null', () => {
            expect(service.totalDemandEnergyTWh()).toBeNull();
        });
    });

    describe('generate', () => {
        it('should POST to the temporal endpoint', async () => {
            const promise = service.generate(MOCK_SCENARIO);
            const req = httpMock.expectOne(ENDPOINT);
            expect(req.request.method).toBe('POST');
            req.flush(MOCK_RESPONSE);
            await tick();
            await promise;
        });

        it('should update peakDemandMW after a successful response', async () => {
            const promise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(ENDPOINT).flush(MOCK_RESPONSE);
            await tick();
            await promise;

            expect(service.peakDemandMW()).not.toBeNull();
            expect(service.peakDemandMW()).toBeGreaterThan(0);
        });

        it('should update totalDemandEnergyTWh after a successful response', async () => {
            const promise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(ENDPOINT).flush(MOCK_RESPONSE);
            await tick();
            await promise;

            expect(service.totalDemandEnergyTWh()).not.toBeNull();
        });

        it('should calculate peak demand as max of MW values', async () => {
            const promise = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(ENDPOINT).flush(MOCK_RESPONSE);
            await tick();
            await promise;

            // max(4000000/1000, 5000000/1000) = 5000
            expect(service.peakDemandMW()).toBe(5000);
        });

        it('should not re-fetch when the same scenario id is used', async () => {
            const p1 = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(ENDPOINT).flush(MOCK_RESPONSE);
            await tick();
            await p1;

            const p2 = service.generate(MOCK_SCENARIO);
            httpMock.expectNone(ENDPOINT);
            await tick();
            await p2;
        });

        it('should re-fetch when the scenario id changes', async () => {
            const p1 = service.generate(MOCK_SCENARIO);
            httpMock.expectOne(ENDPOINT).flush(MOCK_RESPONSE);
            await tick();
            await p1;

            const p2 = service.generate(MOCK_SCENARIO_2);
            httpMock.expectOne(ENDPOINT).flush(MOCK_RESPONSE);
            await tick();
            await p2;
        });
    });
});
