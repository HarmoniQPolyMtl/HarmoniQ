import '@testing-library/jest-dom';
import { getTestBed } from '@angular/core/testing';

/**
 * This beforeEach acts as a safety net: it only resets if the TestBed
 * module is already instantiated (stale state from a previous test).
 */
beforeEach(() => {
  const testBed = getTestBed() as any;
  if (testBed._testModuleRef !== null) {
    testBed.resetTestingModule();
  }
});
