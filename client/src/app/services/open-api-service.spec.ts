import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { OpenApiService } from './open-api-service';

const MOCK_OPENAPI_RESPONSE = {
  components: {
    schemas: {
      HydroelectricDam: { type: 'object', properties: { nom: { type: 'string' } } },
      WindFarm: { type: 'object', properties: { nom: { type: 'string' } } },
    },
  },
};

const OPENAPI_URL = '/openapi.json';

describe('OpenApiService', () => {
  let service: OpenApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        OpenApiService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });

    service = TestBed.inject(OpenApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    vi.clearAllMocks();
  });

  describe('constructor', () => {
    it('should make exactly one GET request to the openapi.json endpoint on init', () => {
      const req = httpMock.expectOne(OPENAPI_URL);
      expect(req.request.method).toBe('GET');
      req.flush(MOCK_OPENAPI_RESPONSE);
    });
  });

  describe('getOpenApiSchemas', () => {
    it('should return undefined before the HTTP response is received', () => {
      expect(service.getOpenApiSchemas()).toBeUndefined();
      httpMock.expectOne(OPENAPI_URL).flush(MOCK_OPENAPI_RESPONSE);
    });

    it('should return the schemas component after the HTTP response', () => {
      httpMock.expectOne(OPENAPI_URL).flush(MOCK_OPENAPI_RESPONSE);

      expect(service.getOpenApiSchemas()).toEqual(MOCK_OPENAPI_RESPONSE.components.schemas);
    });

    it('should return the same cached schemas on subsequent calls', () => {
      httpMock.expectOne(OPENAPI_URL).flush(MOCK_OPENAPI_RESPONSE);

      const first = service.getOpenApiSchemas();
      const second = service.getOpenApiSchemas();

      expect(first).toBe(second);
    });
  });
});
