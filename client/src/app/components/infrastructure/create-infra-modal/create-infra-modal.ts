import { Component, Input, ChangeDetectorRef } from '@angular/core';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';
import { AbstractControl, FormBuilder, FormGroup, ValidationErrors, ValidatorFn, Validators } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule } from '@angular/forms';
import { NgbTooltipModule } from '@ng-bootstrap/ng-bootstrap';
import { SolarInfraForm } from '../solar-infra-form/solar-infra-form';
import { OpenApiService } from '@app/services/open-api-service';
import { ProtectedAreasService } from '@app/services/protected-areas-service';
import { InfrastruturesService } from '@app/services/infrastrutures-service';
import { prettyNames } from '@app/utils/map-utils';

interface FieldDef {
  key: string;
  title: string;
  description?: string;
  enum?: string[];
  type: string;
  readonly: boolean;
  nonNegative: boolean;
  warnIfZero: boolean;
  warningMsg: string;
  errorMsgs: Record<string, string>;
  maxLength?: number;
}

@Component({
  selector: 'app-create-infra-modal',
  imports: [CommonModule, ReactiveFormsModule, NgbTooltipModule, SolarInfraForm],
  templateUrl: './create-infra-modal.html',
  styleUrl: './create-infra-modal.css',
})
export class CreateInfraModal {
  @Input() schema!: any;
  @Input() lat!: number;
  @Input() lon!: number;
  @Input() type!: string;
  @Input() editData: any = null;

  form!: FormGroup;
  fields: FieldDef[] = [];
  prettyName = '';
  improvedTitle = '';
  protectedAreaName: string | null = null;

  isSolar = false;
  isWind = false;
  isOffshore = false;



  constructor(
    public activeModal: NgbActiveModal,
    private fb: FormBuilder,
    private openApiService: OpenApiService,
    private protectedAreasService: ProtectedAreasService,
    private infrasService: InfrastruturesService,
    private cdr: ChangeDetectorRef
  ) { }

  ngOnInit() {
    this.processPrettyName();
    this.buildForm();
    this.protectedAreasService.checkProtectedArea(this.lat, this.lon).then(name => {
      this.protectedAreaName = name;
      this.cdr.detectChanges();
    });

    if (this.isOffshore && this.isWind) {
      if (this.form) {
        this.form.patchValue({ is_offshore: true });
      }
    }
  }




  get isEditMode(): boolean {
    return !!this.editData;
  }

  processPrettyName() {
    const upname = this.type.split('/').pop() || '';
    if (upname === 'hydro') {
      alert("La fonctionnalité pour les infrastructures hydroélectriques est en cours de développement. Cette démonstration est fournie à titre indicatif.");
    }
    this.prettyName = prettyNames[upname] || upname;

    const lowName = this.prettyName.toLowerCase();
    if (this.isEditMode) {
      this.improvedTitle = `Modifier ${lowName}`;
    } else if (lowName.startsWith('centrale')) {
      this.improvedTitle = `Nouvelle ${lowName}`;
    } else {
      this.improvedTitle = `Nouveau ${lowName}`;
    }
    this.improvedTitle = this.improvedTitle.charAt(0).toUpperCase() + this.improvedTitle.slice(1);

  }

  buildForm() {
    const controls: any = {};
    const schemas = this.openApiService.getOpenApiSchemas();
    const props = this.schema.properties;
    const required = this.schema.required || [];
    const typeKey = this.type.split('/').pop() || '';
    this.isSolar = typeKey.toLowerCase() === 'solaire';
    this.isWind = typeKey.toLowerCase() === 'eolienneparc';

    for (const key in props) {

      if (!required.includes(key)) continue;
      if (key === 'id') continue;

      const prop = props[key];
      const isLatLon = key === 'latitude' || key === 'longitude';
      let value: any = '';
      if (this.editData && this.editData[key] !== undefined) {
        value = this.editData[key];
      } else if (key === 'latitude') {
        value = this.lat;
      } else if (key === 'longitude') {
        value = this.lon;
      }

      const initialValue = this.editData ? value : (prop.suggestion ?? value);

      let enumValues: string[] | undefined;
      if (prop['$ref']) {
        const refPath = prop['$ref'].replace('#/components/schemas/', '');
        const enumSchema = schemas[refPath];
        if (enumSchema?.enum) enumValues = enumSchema.enum;
      } else if (prop.enum) {
        enumValues = prop.enum;
      }

      const { validators, errorMsgs, nonNegative, warnIfZero, warningMsg, maxLength } =
        this.resolveValidators(key, prop, typeKey);

      controls[key] = [initialValue, validators];

      this.fields.push({
        key,
        title: prop.title || key.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()),
        description: prop.description,
        enum: enumValues,
        type: (prop.type === 'number' || prop.type === 'integer') ? 'number' : 'text',
        readonly: isLatLon,
        nonNegative,
        warnIfZero,
        warningMsg,
        errorMsgs,
        maxLength,
      });
    }

    if (this.isSolar) {
      if (!controls['panneau_type']) {
        controls['panneau_type'] = [this.editData?.panneau_type || 'biface', []];
      }
      if (!controls['materiau_panneau']) {
        controls['materiau_panneau'] = [this.editData?.materiau_panneau || 'CS6X_300M', []];
      }
      if (!this.editData) {
        if (controls['orientation_panneau']) controls['orientation_panneau'][0] = 180;
        if (controls['angle_panneau']) controls['angle_panneau'][0] = 45;
      }
    }

    if (this.isWind) {
      const offshoreVal = this.editData ? (this.editData.is_offshore === true) : this.isOffshore;
      controls['is_offshore'] = [offshoreVal, []];
    }

    if (this.isSolar) {
      if (!controls['panneau_type']) {
        controls['panneau_type'] = [this.editData?.panneau_type || 'biface', []];
      }
      if (!controls['materiau_panneau']) {
        controls['materiau_panneau'] = [this.editData?.materiau_panneau || 'CS6X_300M', []];
      }
      if (!this.editData) {
        if (controls['orientation_panneau']) controls['orientation_panneau'][0] = 180;
        if (controls['angle_panneau']) controls['angle_panneau'][0] = 45;
      }
    }
    this.form = this.fb.group(controls);

  }

  // ── Event handlers ────────────────────────────────────────────────────────

  onKeydown(event: KeyboardEvent, field: FieldDef) {
    if (field.nonNegative && event.key === '-') {
      event.preventDefault();
    }
  }

  onBlur(field: FieldDef) {
    if (!field.nonNegative) return;
    const control = this.form.get(field.key);
    if (!control) return;
    const val = Number(control.value);
    if (control.value === '' || control.value === null || isNaN(val) || val < 0) {
      control.setValue(0);
    } else if (field.type === 'number') {
      const rounded = Math.round(val * 1000) / 1000;
      if (val !== rounded) {
        control.setValue(rounded);
      }
    }
    control.markAsTouched();
  }

  // ── Error / warning display ───────────────────────────────────────────────

  getFieldError(field: FieldDef): string | null {
    const control = this.form.get(field.key);
    if (!control || !control.errors || !control.touched) return null;
    for (const errKey of Object.keys(control.errors)) {
      if (field.errorMsgs[errKey]) return field.errorMsgs[errKey];
    }
    return 'Valeur invalide.';
  }

  getFieldWarning(field: FieldDef): string | null {
    if (!field.warnIfZero) return null;
    const control = this.form.get(field.key);
    if (!control || control.invalid) return null;
    return Number(control.value) === 0 ? field.warningMsg : null;
  }

  submit() {
    this.activeModal.close(this.form.value);
  }

  // ── Validators ────────────────────────────────────────────────────────────

  private resolveValidators(key: string, prop: any, typeKey: string): {
    validators: ValidatorFn[];
    errorMsgs: Record<string, string>;
    nonNegative: boolean;
    warnIfZero: boolean;
    warningMsg: string;
    maxLength?: number;
  } {
    const validators: ValidatorFn[] = [Validators.required];
    const errorMsgs: Record<string, string> = { required: 'Ce champ est obligatoire.' };
    let nonNegative = false;
    let warnIfZero = false;
    let warningMsg = '';
    let maxLength: number | undefined;

    if (key === 'nom') {
      maxLength = 35;
      validators.push(Validators.maxLength(35));
      errorMsgs['maxlength'] = 'Le nom ne peut pas dépasser 35 caractères.';
      validators.push(this.duplicateNameValidator(typeKey));
      errorMsgs['duplicateName'] = 'Une infrastructure avec ce nom existe déjà.';
      return { validators, errorMsgs, nonNegative, warnIfZero, warningMsg, maxLength };
    }

    const isNumeric = prop.type === 'number' || prop.type === 'integer';
    if (!isNumeric) return { validators, errorMsgs, nonNegative, warnIfZero, warningMsg, maxLength };

    switch (key) {
      case 'nombre_eoliennes':
        nonNegative = true;
        validators.push(Validators.min(0), Validators.max(1000));
        errorMsgs['min'] = "Le nombre d'éoliennes ne peut pas être négatif.";
        errorMsgs['max'] = "Le nombre d'éoliennes ne peut pas dépasser 1 000.";
        warnIfZero = true;
        warningMsg = "Un parc sans éoliennes ne produira pas d'énergie.";
        break;

      case 'capacite_total':
        nonNegative = true;
        validators.push(Validators.min(0), Validators.max(50000));
        errorMsgs['min'] = 'La capacité totale ne peut pas être négative.';
        errorMsgs['max'] = 'La capacité totale ne peut pas dépasser 50 000 MW.';
        break;

      case 'hauteur_moyenne':
        nonNegative = true;
        validators.push(Validators.min(0), Validators.max(300));
        errorMsgs['min'] = 'La hauteur moyenne ne peut pas être négative.';
        errorMsgs['max'] = 'La hauteur moyenne ne peut pas dépasser 300 mètres.';
        break;

      case 'nombre_panneau':
        nonNegative = true;
        validators.push(Validators.min(0), Validators.max(500000));
        errorMsgs['min'] = 'Le nombre de panneaux ne peut pas être négatif.';
        errorMsgs['max'] = 'Le nombre de panneaux ne peut pas dépasser 500 000.';
        warnIfZero = true;
        warningMsg = "Un parc sans panneaux ne produira pas d'énergie.";
        break;

      case 'angle_panneau':
        validators.push(Validators.min(0), Validators.max(90));
        errorMsgs['min'] = "L'angle d'inclinaison doit être compris entre 0° et 90°.";
        errorMsgs['max'] = "L'angle d'inclinaison doit être compris entre 0° et 90°.";
        break;

      case 'orientation_panneau':
        validators.push(Validators.min(0), Validators.max(360));
        errorMsgs['min'] = "L'orientation doit être comprise entre 0° et 360°.";
        errorMsgs['max'] = "L'orientation doit être comprise entre 0° et 360°.";
        break;

      case 'semaine_maintenance':
        validators.push(Validators.min(1), Validators.max(52));
        errorMsgs['min'] = 'La semaine de maintenance doit être un nombre entre 1 et 52.';
        errorMsgs['max'] = 'La semaine de maintenance doit être un nombre entre 1 et 52.';
        break;

      case 'puissance_nominal':
        if (typeKey === 'solaire') {
          nonNegative = true;
          validators.push(Validators.min(0), Validators.max(25));
          errorMsgs['min'] = 'La puissance nominale ne peut pas être négative.';
          errorMsgs['max'] = 'La puissance maximale pour un parc solaire est de 25 MW.';
          warnIfZero = true;
          warningMsg = "Une puissance nominale de 0 MW ne produira pas d'énergie.";
        } else if (typeKey === 'nucleaire') {
          validators.push(Validators.min(300), Validators.max(10000), this.multipleOf300());
          errorMsgs['min'] = 'La puissance minimale est de 300 MW (1 réacteur SMR).';
          errorMsgs['max'] = 'La puissance maximale est de 10 000 MW.';
          errorMsgs['multipleOf300'] = 'La puissance doit être un multiple de 300 MW (ex : 300, 600, 900, 1200…).';
        } else {
          nonNegative = true;
          validators.push(Validators.min(0), Validators.max(50000));
          errorMsgs['min'] = 'La puissance nominale ne peut pas être négative.';
          errorMsgs['max'] = 'La puissance nominale ne peut pas dépasser 50 000 MW.';
          warnIfZero = true;
          warningMsg = "Une puissance nominale de 0 MW ne produira pas d'énergie.";
        }
        break;
    }

    return { validators, errorMsgs, nonNegative, warnIfZero, warningMsg, maxLength };
  }

  private duplicateNameValidator(typeKey: string): ValidatorFn {
    return (control: AbstractControl): ValidationErrors | null => {
      const name = control.value?.trim().toLowerCase();
      if (!name) return null;
      if (this.editData && this.editData.nom?.trim().toLowerCase() === name) return null;
      const exists = this.infrasService.isNameTaken(name);
      return exists ? { duplicateName: true } : null;
    };
  }

  private multipleOf300(): ValidatorFn {
    return (control: AbstractControl): ValidationErrors | null => {
      const val = Number(control.value);
      if (!val || isNaN(val)) return null;
      return val % 300 === 0 ? null : { multipleOf300: true };
    };
  }
}
