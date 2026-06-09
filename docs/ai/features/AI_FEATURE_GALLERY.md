# AI FEATURE: GALLERY
The Gallery is the "Visual Memory" of the system, providing a managed library for user uploads and AI-generated imagery.

## 1. Asset Indexing & Storage
- **Deduplication:** Every image is hashed using **SHA-256**. If a file with the same hash already exists, the system creates a link to the existing record rather than duplicating the file on disk.
- **Metadata Extraction:** Upon upload, the system extracts EXIF data (dimensions, camera make/model, GPS coordinates) to provide the AI with physical context for the image.
- **Storage:** Images are stored in `data/generated_images` with sanitized filenames to prevent path traversal.

## 2. AI Visual Tools
The Gallery integrates directly with the system's Diffusion servers:
- **AI Upscaling:** Sends the image to a specialized `/images/upscale` endpoint to increase resolution while maintaining detail.
- **Style Transfer (`img2img`):** Transforms an existing image based on a new prompt and a "strength" parameter (controlling how much of the original structure is preserved).
- **Auto-Tagging:** Uses Vision-Language (VL) models to generate `ai_tags` (e.g., "cyberpunk", "sunset"), making the gallery searchable by visual content.

## 3. Organization
- **Albums:** Logical groupings of images for project-based organization.
- **Favorites:** A binary flag for high-value assets.
- **Advanced Filtering:** Supports queries by AI tags, user tags, or the specific model used to generate the image.

## 4. AI Implementation Notes
When managing the gallery, the AI should:
1.  **Suggest Upscaling:** If a user wants to use a generated image in a high-resolution document, suggest upscaling it first.
2.  **Iterate via Style Transfer:** Instead of regenerating from scratch, use style transfer to refine a visual concept the user already likes.
3.  **Categorize via Tags:** Use `ai_tags` to help the user find "that one image of the blue city" without requiring exact filenames.