import os
import json
import traceback
import time
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

if "GEMINI_API_KEY" not in os.environ:
    raise ValueError("Please set the GEMINI_API_KEY environment variable.")

client = genai.Client()

# Configuration tracking state
MANIFEST_CACHE_FILE = ".manifest_cache.json"
GEMINI_MODEL = "gemini-3-flash-preview"

# 1. Read the grounding architectural requirements blueprint
with open("blueprint.txt", "r") as f:
    blueprint = f.read()

# Strict Pydantic models for structured output targeting Developer API mode
class FileManifest(BaseModel):
    filepaths: list[str] = Field(
        description="A comprehensive list of all relative file paths needed to satisfy the microservices blueprint architecture."
    )

class SingleFilePayload(BaseModel):
    content: str = Field(
        description="The full, un-truncated production-grade source code string for the requested file path."
    )

try:
    # STEP A: Discovery Matrix — Check cache or query model
    if os.path.exists(MANIFEST_CACHE_FILE):
        print("💾 Found existing manifest cache file. Loading target structure...")
        with open(MANIFEST_CACHE_FILE, "r") as mc:
            target_files = json.load(mc)
    else:
        print("📋 Analyzing blueprint and discovering target workspace manifests...")
        manifest_response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"Analyze this blueprint and output a list of ALL file paths needed to form the complete project: {blueprint}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FileManifest,
                temperature=0.1,
            ),
        )
        manifest = json.loads(manifest_response.text)
        target_files = manifest.get("filepaths", [])
        
        # Save cache immediately to pin down the 41 indexes
        with open(MANIFEST_CACHE_FILE, "w") as mc:
            json.dump(target_files, mc)

    print(f"🎯 Total structural indexes identified: {len(target_files)}\n")

    # STEP B: File Scaffolder Loop with Fault Tolerance and Model Fallback Hierarchy
    for index, path in enumerate(target_files, start=1):
        
        # 🟢 CHECKPOINT: Skip if file already exists and is not empty
        if os.path.exists(path) and os.path.getsize(path) > 0:
            print(f"⏭️  [{index}/{len(target_files)}] Skipping already generated file: '{path}'")
            continue
            
        print(f"🚀 [{index}/{len(target_files)}] Generating clean source for: '{path}'...")
        
        prompt = f"""
        Context: You are writing the code for a multi-tenant FastAPI system using FastMCP and uv.
        Original Blueprint: {blueprint}
        
        Task: Provide the complete, production-grade file contents for the file path: '{path}'.
        Ensure all internal imports, error handlings, models, and dependencies match other related service layers perfectly. 
        Do not shorten the code with comments like '# implement later'.
        """

        # Define model execution fallback sequence order
        model_pool = [GEMINI_MODEL, 'gemini-2.5-flash', 'gemini-3.5-flash', 'gemini-flash-lite-latest', 'gemini-2.5-flash-lite', 'gemini-3.5-flash-lite']
        source_code = None
        
        for active_model in model_pool:
            try:
                if active_model != model_pool[0]:
                    print(f"🔄 Switching models... Attempting extraction using alternative tier: {active_model}")
                
                file_response = client.models.generate_content(
                    model=active_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=SingleFilePayload,
                        temperature=0.2,
                    ),
                )
                
                payload = json.loads(file_response.text)
                source_code = payload.get("content", "").strip()
                
                # If generation successful, break model retry pool loop
                if source_code:
                    break
                    
            except Exception as model_err:
                print(f"⚠️  Model {active_model} failed index execution loop: {str(model_err)}")
                # Quick linear backoff sleep before changing tiers or retrying
                time.sleep(2)
                continue

        # If all model pools failed to output source for this index block
        if not source_code:
            print(f"❌ Error: Index {index} [{path}] completely exhausted model tier configurations. Pausing loop pipeline execution.")
            break

        # Clean markdown wrap artifacts if present
        if source_code.startswith("```"):
            lines = source_code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            source_code = "\n".join(lines)
            
        # Natively map directory hierarchy structures
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            
        with open(path, "w", encoding="utf-8") as file_sink:
            file_sink.write(source_code)
        print(f"  └─ Target file successfully written to workspace.")

    print("\n🎉 Architecture synchronization execution state finalized.")

except Exception as e:
    print(f"\n❌ Execution Failed: {str(e)}")
    traceback.print_exc()