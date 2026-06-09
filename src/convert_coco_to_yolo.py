#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Konvertiert COCO-Format (result.json) zu YOLO-Format (.txt Dateien)

COCO: bbox = [x, y, width, height] (absolute Pixel)
YOLO: class_id x_center y_center width height (normalisiert 0-1)
"""

import json
import os
from pathlib import Path


def convert_coco_to_yolo(coco_json_path, images_dir, output_labels_dir):
    """
    Konvertiert COCO result.json zu YOLO .txt Dateien
    
    Args:
        coco_json_path: Pfad zur result.json (COCO-Format)
        images_dir: Ordner mit Bildern
        output_labels_dir: Ordner wo .txt Dateien gespeichert werden
    """
    
    # Ausgabe-Ordner erstellen
    Path(output_labels_dir).mkdir(parents=True, exist_ok=True)
    
    # COCO JSON laden
    print(f"📖 Lade COCO JSON: {coco_json_path}")
    with open(coco_json_path, 'r') as f:
        coco_data = json.load(f)
    
    # COCO Struktur:
    # - images: [{"id": 0, "file_name": "...", "width": 640, "height": 480}, ...]
    # - annotations: [{"id": 0, "image_id": 0, "category_id": 0, "bbox": [x, y, w, h]}, ...]
    # - categories: [{"id": 0, "name": "license_plate"}, ...]
    
    images_dict = {img['id']: img for img in coco_data.get('images', [])}
    annotations = coco_data.get('annotations', [])
    categories = {cat['id']: cat['name'] for cat in coco_data.get('categories', [])}
    
    print(f"📊 Gefunden: {len(images_dict)} Bilder, {len(annotations)} Annotations")
    print(f"🏷️  Klassen: {categories}")
    
    # Pro Bild eine .txt Datei erstellen
    annotations_by_image = {}
    for ann in annotations:
        img_id = ann['image_id']
        if img_id not in annotations_by_image:
            annotations_by_image[img_id] = []
        annotations_by_image[img_id].append(ann)
    
    converted_count = 0
    
    for image_id, image_info in images_dict.items():
        img_width = image_info['width']
        img_height = image_info['height']
        
        # Originalen Dateinamen extrahieren (aus dem komplexen Path)
        original_filename = image_info['file_name']
        # Beispiel: "..\\..\\label-studio\\label-studio\\media\\upload\\3\\d29dae17-PASST_20260511_101956_569460_0005.jpg"
        # Wir brauchen nur: "d29dae17-PASST_20260511_101956_569460_0005.jpg"
        simple_filename = Path(original_filename).name
        
        # YOLO .txt Pfad (ohne Extension)
        txt_path = Path(output_labels_dir) / simple_filename.replace('.jpg', '.txt').replace('.png', '.txt')
        
        # Annotations für dieses Bild sammeln
        yolo_lines = []
        if image_id in annotations_by_image:
            for ann in annotations_by_image[image_id]:
                class_id = ann['category_id']
                bbox = ann['bbox']  # [x, y, width, height]
                
                # COCO → YOLO konvertieren
                x, y, w, h = bbox
                
                # Normalisierte Koordinaten (0-1)
                x_center = (x + w / 2) / img_width
                y_center = (y + h / 2) / img_height
                w_norm = w / img_width
                h_norm = h / img_height
                
                # YOLO Format: class_id x_center y_center width height
                yolo_line = f"{class_id} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}"
                yolo_lines.append(yolo_line)
        
        # .txt Datei speichern (auch wenn leer - für Konsistenz)
        with open(txt_path, 'w') as f:
            f.write('\n'.join(yolo_lines))
        
        converted_count += 1
        if converted_count % 50 == 0:
            print(f"  ✓ {converted_count} Bilder konvertiert...")
    
    print(f"\n✅ Fertig! {converted_count} YOLO-Label-Dateien erstellt in: {output_labels_dir}")
    return converted_count


if __name__ == "__main__":
    # Pfade anpassen
    project_root = Path(__file__).parent.parent
    
    # Deine Gruppe
    coco_json = project_root / "data" / "my_labelstudio" / "result.json"
    images_dir = project_root / "data" / "my_labelstudio" / "images"
    labels_dir = project_root / "data" / "my_labelstudio" / "labels"
    
    if coco_json.exists():
        print("🔄 Konvertiere deine COCO-Bilder zu YOLO-Format...\n")
        convert_coco_to_yolo(str(coco_json), str(images_dir), str(labels_dir))
    else:
        print(f"❌ Fehler: {coco_json} nicht gefunden!")
        print(f"   Bitte speichern unter: {coco_json}")
