#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Merged alle Trainings-Bilder (positiv + negativ) und erstellt Train/Val Split
mit YOLO-Struktur

Struktur nach dem Script:
data/
├── train/
│   ├── images/
│   └── labels/
├── val/
│   ├── images/
│   └── labels/
└── data.yaml
"""

import shutil
import json
import random
from pathlib import Path
from collections import defaultdict


def merge_datasets():
    """Merged Daten von 3 Quellen in unified YOLO-Format"""
    
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"
    
    # Quellen
    my_labelstudio = data_dir / "my_labelstudio"
    other_team = Path("C:\\Users\\z00431uw\\Desktop\\RDF\\IT_Malassa\\Projektarbeit_2 Parkhaus\\03_gelabelte Bildre von anderen Gruppe")
    negative_images = Path("C:\\Users\\z00431uw\\Desktop\\RDF\\IT_Malassa\\Projektarbeit_2 Parkhaus\\02_Nicht passende Bilder Andi und Chris")
    
    # Ziele
    train_images = data_dir / "train" / "images"
    train_labels = data_dir / "train" / "labels"
    val_images = data_dir / "val" / "images"
    val_labels = data_dir / "val" / "labels"
    
    # Ordner erstellen
    for folder in [train_images, train_labels, val_images, val_labels]:
        folder.mkdir(parents=True, exist_ok=True)
    
    print("🔄 Starte Dataset-Merging...\n")
    
    # Alle Bilder + Labels sammeln
    all_images = []
    
    # === 1. Deine Bilder ===
    print(f"📂 Lese deine Bilder: {my_labelstudio}")
    if my_labelstudio.exists():
        my_images = list((my_labelstudio / "images").glob("*.*"))
        print(f"  ✓ {len(my_images)} Bilder gefunden")
        for img_path in my_images:
            label_path = my_labelstudio / "labels" / img_path.stem
            label_path = label_path.with_suffix('.txt')
            all_images.append((img_path, label_path, "my_team"))
    
    # === 2. Andere Team ===
    print(f"\n📂 Lese Bilder von anderer Gruppe: {other_team}")
    if other_team.exists():
        other_images = list((other_team / "images").glob("*.*"))
        print(f"  ✓ {len(other_images)} Bilder gefunden")
        for img_path in other_images:
            label_path = other_team / "labels" / img_path.stem
            label_path = label_path.with_suffix('.txt')
            all_images.append((img_path, label_path, "other_team"))
    
    # === 3. Negative Bilder (leere Labels) ===
    print(f"\n📂 Lese negative Bilder (kein Kennzeichen): {negative_images}")
    if negative_images.exists():
        neg_images = list(negative_images.glob("*.*"))
        print(f"  ✓ {len(neg_images)} negative Bilder gefunden")
        for img_path in neg_images:
            if img_path.is_file() and img_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                all_images.append((img_path, None, "negative"))  # None = kein Label
    
    print(f"\n{'='*60}")
    print(f"📊 GESAMT: {len(all_images)} Trainings-Bilder")
    print(f"{'='*60}\n")
    
    # Train/Val Split (80/20)
    random.shuffle(all_images)
    split_point = int(len(all_images) * 0.8)
    
    train_set = all_images[:split_point]
    val_set = all_images[split_point:]
    
    print(f"📋 Split:")
    print(f"  Training: {len(train_set)} Bilder (80%)")
    print(f"  Validation: {len(val_set)} Bilder (20%)\n")
    
    # Kopiere Train-Bilder
    print(f"📋 Kopiere Training-Bilder...")
    for src_img, src_label, source in train_set:
        # Eindeutigen Namen geben (Kollisionen vermeiden)
        dest_name = f"{source}_{src_img.name}"
        
        # Bild kopieren
        shutil.copy2(src_img, train_images / dest_name)
        
        # Label kopieren (oder leere Datei erstellen)
        if src_label and src_label.exists():
            with open(src_label, 'r') as f:
                label_content = f.read()
            with open(train_labels / dest_name.replace(src_img.suffix, '.txt'), 'w') as f:
                f.write(label_content)
        else:
            # Leere Label für negative Bilder
            with open(train_labels / dest_name.replace(src_img.suffix, '.txt'), 'w') as f:
                f.write("")
    
    # Kopiere Val-Bilder
    print(f"📋 Kopiere Validation-Bilder...")
    for src_img, src_label, source in val_set:
        dest_name = f"{source}_{src_img.name}"
        
        # Bild kopieren
        shutil.copy2(src_img, val_images / dest_name)
        
        # Label kopieren (oder leere Datei erstellen)
        if src_label and src_label.exists():
            with open(src_label, 'r') as f:
                label_content = f.read()
            with open(val_labels / dest_name.replace(src_img.suffix, '.txt'), 'w') as f:
                f.write(label_content)
        else:
            with open(val_labels / dest_name.replace(src_img.suffix, '.txt'), 'w') as f:
                f.write("")
    
    print(f"\n✅ Bilder & Labels kopiert!")
    
    # === Erstelle data.yaml ===
    data_yaml = {
        'path': str(data_dir.absolute()),
        'train': 'train/images',
        'val': 'val/images',
        'nc': 1,  # Number of classes
        'names': ['license_plate']  # Class names
    }
    
    yaml_path = data_dir / "data.yaml"
    
    # Speichere als YAML
    import yaml
    with open(yaml_path, 'w') as f:
        yaml.dump(data_yaml, f, default_flow_style=False)
    
    print(f"\n📝 Erstelle data.yaml...")
    print(f"""
path: {data_dir}
train: train/images
val: val/images
nc: 1
names:
  - license_plate
""")
    
    print(f"\n{'='*60}")
    print(f"✅ FERTIG! YOLO-Dataset erstellt!")
    print(f"{'='*60}")
    print(f"\n📁 Struktur:")
    print(f"  data/")
    print(f"  ├── train/images/ ({len(list(train_images.glob('*')))} Bilder)")
    print(f"  ├── train/labels/")
    print(f"  ├── val/images/ ({len(list(val_images.glob('*')))} Bilder)")
    print(f"  ├── val/labels/")
    print(f"  └── data.yaml ✅")
    print(f"\n🚀 Bereit zum Trainieren mit:")
    print(f"   model = YOLO('yolov8n.pt')")
    print(f"   model.train(data='data/data.yaml', epochs=100)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    try:
        merge_datasets()
    except ImportError:
        print("❌ PyYAML nicht installiert!")
        print("Installiere mit: pip install pyyaml")
    except Exception as e:
        print(f"❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
