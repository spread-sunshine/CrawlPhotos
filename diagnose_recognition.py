# -*- coding: utf-8 -*-
"""Diagnose why all photos fail face recognition."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.dont_write_bytecode = True

from app.config.settings import Settings
from app.face_recognition.facade import FaceRecognizerFacade
from app.face_recognition.models import TargetConfig


async def main():
    settings = Settings.load()

    print("=" * 60)
    print("1. FACE RECOGNITION CONFIG")
    fc = settings.get_section("face_recognition")
    print(f"   Provider: {fc.get('provider')}")
    print(f"   Provider config keys: {list(fc.keys())}")

    print("\n" + "=" * 60)
    print("2. TARGET CONFIG")
    targets_cfg = fc.get("targets", [])
    print(f"   Target count: {len(targets_cfg)}")
    for i, tc in enumerate(targets_cfg):
        name = tc.get("name", "Unknown")
        enabled = tc.get("enabled")
        min_conf = tc.get("min_confidence")
        ref_dir = tc.get("reference_photos_dir", "")
        ref_path = Path(ref_dir)
        exists = ref_path.exists()
        files = []
        if exists:
            exts = {".jpg", ".jpeg", ".png", ".webp"}
            files = [p.name for p in sorted(ref_path.iterdir())
                     if p.suffix.lower() in exts]
        print(f"\n   Target[{i}]: {name}")
        print(f"     enabled={enabled}, min_confidence={min_conf}")
        print(f"     ref_dir='{ref_dir}'")
        print(f"     dir_exists={exists}, ref_files={files}")

    print("\n" + "=" * 60)
    print("3. CREATE FACADE & INITIALIZE")
    recognizer = FaceRecognizerFacade(fc)
    print(f"   Facade created, provider type: {recognizer.current_provider_info.provider_type.value}")

    # Build TargetConfig list
    targets = []
    for tc in targets_cfg:
        ref_dir_str = tc.get("reference_photos_dir", "")
        ref_dir_path = Path(ref_dir_str) if ref_dir_str else None
        ref_paths = []
        if ref_dir_path and ref_dir_path.exists():
            exts = {".jpg", ".jpeg", ".png", ".webp"}
            ref_paths = [p for p in sorted(ref_dir_path.iterdir())
                        if p.suffix.lower() in exts]
        target = TargetConfig(
            name=tc.get("name", "Unknown"),
            reference_photo_paths=ref_paths,
            min_confidence=tc.get("min_confidence", 0.80),
            enabled=tc.get("enabled", True),
        )
        targets.append(target)
        print(f"   Target '{target.name}': {len(ref_paths)} ref photos, "
              f"enabled={target.enabled}, min_conf={target.min_confidence}")

    try:
        init_ok = await recognizer.initialize(targets)
        print(f"   Initialize result: {init_ok}")
    except Exception as e:
        print(f"   Initialize FAILED: {type(e).__name__}: {e}")
        return

    print("\n" + "=" * 60)
    print("4. HEALTH CHECK")
    hc = await recognizer.health_check()
    print(f"   Health: {hc}")

    print("\n" + "=" * 60)
    print("5. LIST TARGETS (after init)")
    listed = await recognizer._recognizer.list_targets()
    for t in listed:
        print(f"   {t}")

    print("\n" + "=" * 60)
    print("6. TEST RECOGNITION on a real photo")
    test_img = Path("data/temp/9.jpg.tmp")
    if not test_img.exists():
        # Try any file in data/temp
        temp_dir = Path("data/temp")
        if temp_dir.exists():
            files = sorted(temp_dir.glob("*.tmp"))
            if files:
                test_img = files[0]
    print(f"   Test image: {test_img}")
    print(f"   Exists: {test_img.exists()}")

    if test_img.exists():
        result = await recognizer.recognize(str(test_img))
        print(f"   contains_target: {result.contains_target}")
        print(f"   best_confidence: {result.best_confidence}")
        print(f"   total_faces_detected: {result.total_faces_detected}")
        print(f"   provider_name: {result.provider_name}")
        print(f"   raw_response: {result.raw_response}")
        print(f"   processing_time_ms: {result.processing_time_ms:.1f}")
        if result.all_face_detections:
            for fd in result.all_face_detections[:5]:
                print(f"   Face detected: conf={fd.confidence:.4f}, box={fd.bounding_box.to_dict()}")

        # Debug: manually compute similarities for each detected face
        import cv2
        import numpy as np
        provider = recognizer._recognizer
        img = cv2.imread(str(test_img))
        loop = asyncio.get_event_loop()
        faces = await loop.run_in_executor(None, lambda i=img: provider._app.get(i))

        print("\n   === DETAILED SIMILARITY ANALYSIS ===")
        ref_embs = provider._target_embeddings.get("宝贝女儿", [])
        print(f"   Reference embeddings count: {len(ref_embs)}")
        
        for idx, f in enumerate(faces):
            emb = f.embedding
            if emb is None:
                continue
            det_conf = float(f.det_score)
            sims = []
            for ri, ref_emb in enumerate(ref_embs):
                dot = float(np.dot(emb, ref_emb))
                norm_a = float(np.linalg.norm(emb))
                norm_b = float(np.linalg.norm(ref_emb))
                cos_sim = dot / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0.0
                sims.append(cos_sim)
                print(f"   Face[{idx}] vs Ref[{ri}]: cos_sim={cos_sim:.6f} "
                      f"(det_conf={det_conf:.4f})")
            max_sim = max(sims) if sims else 0
            print(f"   Face[{idx}] BEST sim={max_sim:.6f}, "
                  f"passes_0.8={max_sim >= 0.8}")
    else:
        print("   SKIP - no test image found")

    print("\n" + "=" * 60)
    await recognizer.cleanup()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
