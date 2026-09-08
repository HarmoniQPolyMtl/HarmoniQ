import { Component, OnInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { Router } from '@angular/router';

@Component({
  selector: 'app-home-page',
  imports: [],
  templateUrl: './home-page.html',
  styleUrl: './home-page.css',
})
export class HomePage implements OnInit, OnDestroy {
  @ViewChild('layer1', { static: true }) layer1!: ElementRef<HTMLDivElement>;
  @ViewChild('layer2', { static: true }) layer2!: ElementRef<HTMLDivElement>;

  backgrounds = [
    '/home-screen/barrage-hydro.avif',
    '/home-screen/eolienne.jpeg',
    '/home-screen/solar-park-quebec.jpg',
    'https://images.pexels.com/photos/414837/pexels-photo-414837.jpeg',
    'https://images.pexels.com/photos/31326222/pexels-photo-31326222/free-photo-of-aerial-view-of-dam-structure-in-alma-wi.jpeg',
    'https://images.pexels.com/photos/257700/pexels-photo-257700.jpeg',
    'https://images.pexels.com/photos/356036/pexels-photo-356036.jpeg',
    'https://images.pexels.com/photos/3044472/pexels-photo-3044472.jpeg'
  ];

  currentBgIndex = 0;
  nextBgIndex = 0;
  isFirstLayerVisible = true;
  private rotationInterval: any;

  constructor(private router: Router) { }

  ngOnInit() {
    this.currentBgIndex = Math.floor(Math.random() * this.backgrounds.length);
    this.nextBgIndex = this.currentBgIndex;

    this.setLayerBg(this.layer1, this.currentBgIndex);

    this.rotationInterval = setInterval(() => this.rotateBackground(), 5000);
  }

  ngOnDestroy() {
    if (this.rotationInterval) clearInterval(this.rotationInterval);
  }

  private setLayerBg(layer: ElementRef<HTMLDivElement>, index: number) {
    layer.nativeElement.style.backgroundImage = `url('${this.backgrounds[index]}')`;
  }

  rotateBackground() {
    const visibleIndex = this.isFirstLayerVisible ? this.currentBgIndex : this.nextBgIndex;
    const nextIndex = (visibleIndex + 1) % this.backgrounds.length;

    if (this.isFirstLayerVisible) {
      this.nextBgIndex = nextIndex;
      this.setLayerBg(this.layer2, nextIndex);
    } else {
      this.currentBgIndex = nextIndex;
      this.setLayerBg(this.layer1, nextIndex);
    }

    setTimeout(() => {
      this.isFirstLayerVisible = !this.isFirstLayerVisible;
      this.layer1.nativeElement.classList.toggle('hidden', !this.isFirstLayerVisible);
      this.layer2.nativeElement.classList.toggle('hidden', this.isFirstLayerVisible);
    }, 50);
  }

  navigate(path: string) {
    this.router.navigate([path]);
  }
}