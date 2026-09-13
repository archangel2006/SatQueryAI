from __future__ import annotations

from app.io.geotiff import ALLOWED_EXTS, extension_of, is_allowed_filename, preview_from_bytes
from app.schemas import CompatibilityResult, JobType


def check_compatibility(
    job: JobType,
    files: list[tuple[str, bytes]],
    *,
    ordered_modalities: bool = False,
) -> CompatibilityResult:
    """Hard gate before any model call. Never raises for validation failures."""
    if job == "ask_scene":
        if len(files) != 1:
            return CompatibilityResult(
                valid=False,
                error="Ask this scene needs exactly one image.",
            )
        filename, data = files[0]
        if not filename or not is_allowed_filename(filename):
            return CompatibilityResult(
                valid=False,
                error="Please use GeoTIFF (.tif/.tiff), or PNG/JPEG for official practice images.",
            )
        try:
            _, meta = preview_from_bytes(data, filename)
        except Exception as exc:  # noqa: BLE001 — surface as compatibility error
            return CompatibilityResult(valid=False, error=str(exc))

        note = None
        if extension_of(filename) not in {".tif", ".tiff"}:
            note = "Benchmark image · no CRS"
        return CompatibilityResult(
            valid=True,
            metadata=meta,
            extras={"note": note} if note else {},
        )

    if job == "optical_sar":
        if len(files) != 2:
            return CompatibilityResult(
                valid=False,
                error="Optical + SAR analysis needs exactly two images.",
            )

        metadata = []
        for filename, data in files:
            if not filename or not is_allowed_filename(filename):
                return CompatibilityResult(
                    valid=False,
                    error="Please use GeoTIFF (.tif/.tiff), or PNG/JPEG for official practice images.",
                )
            try:
                _, image_metadata = preview_from_bytes(data, filename)
            except Exception as exc:  # noqa: BLE001 — surface as compatibility error
                return CompatibilityResult(valid=False, error=str(exc))
            metadata.append(image_metadata)

        modalities = [item.modality_guess for item in metadata]
        if not ordered_modalities and sorted(modalities) != ["optical", "sar"]:
            return CompatibilityResult(
                valid=False,
                error=(
                    "Optical + SAR analysis needs one optical image and one SAR image. "
                    f"Detected: {modalities[0]} and {modalities[1]}. "
                    "Use a multi-band optical raster and a SAR raster with VV/VH or SAR metadata."
                ),
                extras={
                    "modalities": modalities,
                    "files": [item.model_dump() for item in metadata],
                },
            )

        dimensions = {(item.width, item.height) for item in metadata}
        if len(dimensions) != 1:
            return CompatibilityResult(
                valid=False,
                error=(
                    "Optical and SAR images must have matching dimensions for this baseline. "
                    f"Detected: {metadata[0].width}x{metadata[0].height} and "
                    f"{metadata[1].width}x{metadata[1].height}."
                ),
                extras={"dimensions": [[item.width, item.height] for item in metadata]},
            )

        output_modalities = ["optical", "sar"] if ordered_modalities else modalities
        optical_metadata = metadata[0] if ordered_modalities else next(
            item for item in metadata if item.modality_guess == "optical"
        )
        return CompatibilityResult(
            valid=True,
            metadata=optical_metadata,
            extras={
                "files": [item.model_dump() for item in metadata],
                "modalities": output_modalities,
                "detected_modalities": modalities,
            },
        )

    if job == "before_after":
        if len(files) != 2:
            return CompatibilityResult(
                valid=False,
                error="Before vs After analysis needs exactly two images.",
            )
        metadata = []
        for filename, data in files:
            if not filename or not is_allowed_filename(filename):
                return CompatibilityResult(
                    valid=False,
                    error="Please use GeoTIFF (.tif/.tiff), or PNG/JPEG for benchmark images.",
                )
            try:
                _, image_metadata = preview_from_bytes(data, filename)
            except Exception as exc:  # noqa: BLE001
                return CompatibilityResult(valid=False, error=str(exc))
            metadata.append(image_metadata)
        if {(item.width, item.height) for item in metadata} != {(metadata[0].width, metadata[0].height)}:
            return CompatibilityResult(
                valid=False,
                error=(
                    "Images must have matching dimensions. Detected: "
                    f"{metadata[0].width}x{metadata[0].height} and "
                    f"{metadata[1].width}x{metadata[1].height}."
                ),
                extras={"files": [item.model_dump() for item in metadata]},
            )
        return CompatibilityResult(
            valid=True,
            metadata=metadata[0],
            extras={"files": [item.model_dump() for item in metadata]},
        )

    return CompatibilityResult(valid=False, error=f"Unsupported job: {job}")


def allowed_extensions() -> set[str]:
    return set(ALLOWED_EXTS)
