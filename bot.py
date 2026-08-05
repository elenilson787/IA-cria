import modal

image = (
    modal.Image.debian_slim(python_version="3.10").pip_install(
        "torch",
        "diffusers",
        "transformers",
        "accelerate",
        "sentencepiece",
        "pillow",
        "fastapi",
        "opencv-python-headless",
        "imageio-ffmpeg",
    )
)

app = modal.App("tiktok-video-generator", image=image)


@app.cls(gpu="L4", timeout=600)
class VideoModel:

    @modal.enter()
    def load_model(self):
        import torch
        from diffusers import StableVideoDiffusionPipeline

        print("⚡ Carregando modelo Stable Video Diffusion...")
        self.pipe = StableVideoDiffusionPipeline.from_pretrained(
            "stabilityai/stable-video-diffusion-img2vid-xt",
            torch_dtype=torch.float16,
            variant="fp16",
        )
        self.pipe.enable_model_cpu_offload()

    @modal.fastapi_endpoint(method="POST")
    def generate(self, data: dict):
        import base64
        import io

        from diffusers.utils import export_to_video
        from fastapi.responses import Response
        from PIL import Image

        image_b64 = data.get("image_base64", "")

        if not image_b64:
            return Response(
                content="Imagem em Base64 ausente", status_code=400
            )

        image_bytes = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # 📐 Redimensiona para VERTICAL 9:16 (576 largura x 1024 altura)
        image = image.resize((576, 1024))

        print("🎬 Gerando vídeo vertical 9:16 para TikTok/Reels...")

        frames = self.pipe(
            image,
            decode_chunk_size=8,
            motion_bucket_id=180,  # Aumentado para gerar mais movimento
            fps=7,
        ).frames[0]

        video_path = "/tmp/output.mp4"
        export_to_video(frames, video_path, fps=7)

        with open(video_path, "rb") as f:
            video_bytes = f.read()

        return Response(content=video_bytes, media_type="video/mp4")
