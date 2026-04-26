from fastapi import FastAPI
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import HTTPException
import pandas as pd
import json
import io
app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.post("/DataUpload")
async def data_upload(file: UploadFile = File(...)):
    if file.filename.endswith(".csv"):
        try:
            contents = await file.read()
            df = pd.read_csv(io.BytesIO(contents))

            description = df.describe()

            result = {
                "filename": file.filename,
                "rows": len(df),
                "columns": len(df.columns),
                "column_names": df.columns.tolist(),
                "description": description.to_dict(),
                "data_preview": df.head().to_dict(orient='records')
            }

            return result
        except Exception as e:
            return {"error": str(e)}
    else:
        raise HTTPException(status_code=400, detail="File type not supported")

