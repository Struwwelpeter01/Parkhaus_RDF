#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
YOLO Modell Training für Kennzeichen-Erkennung

Modell-Größen:
- n (nano): Schnell, kleine Dateien (Raspberry Pi)
- m (medium): Gutes Mittelmaß
- l (large): Höhere Genauigkeit
- x (xlarge): Beste Genauigkeit, aber langsam
"""

from ultralytics import YOLO
from pathlib import Path
import sys


def train_yolo(model_size='m', epochs=100, batch_size=16, device=0):
    """
    Trainiere YOLO-Modell für Kennzeichen-Erkennung
    
    Args:
        model_size: 'n', 'm', 'l', oder 'x'
        epochs: Anzahl Durchläufe (50-150 typical)
        batch_size: Bilder pro Batch (8-32)
        device: GPU-Nummer (0 = erste GPU, 'cpu' = CPU nur)
    """
    
    project_root = Path(__file__).parent.parent
    data_yaml = project_root / "data" / "data.yaml"
    
    if not data_yaml.exists():
        print(f"❌ Fehler: {data_yaml} nicht gefunden!")
        print("   Führe zuerst aus: python src/merge_and_split_datasets.py")
        sys.exit(1)
    
    print("\n" + "="*70)
    print("🚗 YOLO Kennzeichen-Erkennung Training")
    print("="*70)
    print(f"\n📊 Konfiguration:")
    print(f"  Modell: YOLOv8{model_size}")
    print(f"  Epochs: {epochs}")
    print(f"  Batch Size: {batch_size}")
    print(f"  Device: {'GPU' if device != 'cpu' else 'CPU'}")
    print(f"  Data: {data_yaml}\n")
    
    # Lade Pre-trained Modell
    print(f"⏳ Lade YOLOv8{model_size}...")
    model = YOLO(f'yolov8{model_size}.pt')
    
    # Trainiere
    print(f"🚀 Starte Training...\n")
    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=640,
        batch=batch_size,
        patience=20,  # Early stopping nach 20 Epochen ohne Verbesserung
        device=device,
        name='license_plate_detection',
        project=str(project_root / "runs" / "detect"),
        save=True,
        verbose=True,
        # Augmentation
        augment=True,
        flipud=0.5,  # 50% vertikal spiegeln
        fliplr=0.5,  # 50% horizontal spiegeln
        mosaic=1.0,  # Mosaic-Augmentation
    )
    
    # Results anzeigen
    print(f"\n{'='*70}")
    print(f"✅ TRAINING FERTIG!")
    print(f"{'='*70}")
    print(f"\n📁 Ergebnisse gespeichert in:")
    print(f"   runs/detect/license_plate_detection/")
    print(f"\n📊 Beste Modell:")
    print(f"   {project_root / 'runs' / 'detect' / 'license_plate_detection' / 'weights' / 'best.pt'}")
    print(f"\n💾 Zuletzt trainiertes Modell:")
    print(f"   {project_root / 'runs' / 'detect' / 'license_plate_detection' / 'weights' / 'last.pt'}")
    
    print(f"\n🎯 Um das Modell zu verwenden:")
    print(f"""
from ultralytics import YOLO

# Lade das beste Modell
model = YOLO('runs/detect/license_plate_detection/weights/best.pt')

# Erkenne in Bild
results = model.predict(source='bild.jpg', conf=0.5)

# Oder in Video/Webcam
results = model.predict(source=0)  # 0 = Webcam
""")
    
    print(f"{'='*70}\n")
    
    return model, results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='YOLO Kennzeichen Training')
    parser.add_argument('--model', type=str, default='m', choices=['n', 'm', 'l', 'x'],
                        help='Modell-Größe: n(ano), m(edium), l(arge), x(large)')
    parser.add_argument('--epochs', type=int, default=100,
                        help='Anzahl Epochen (default: 100)')
    parser.add_argument('--batch', type=int, default=16,
                        help='Batch Size (default: 16)')
    parser.add_argument('--device', type=str, default='0',
                        help='Device: 0 (GPU), cpu, oder GPU-Nummer')
    
    args = parser.parse_args()
    
    # String zu int konvertieren wenn möglich
    device = int(args.device) if args.device.isdigit() else args.device
    
    train_yolo(
        model_size=args.model,
        epochs=args.epochs,
        batch_size=args.batch,
        device=device
    )
