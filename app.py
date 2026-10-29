"""AI Trade Analysis - Flask REST API + web UI.

Endpoints
  GET    /                      web interface
  GET    /api/health            status (db, llm provider, knowledge-base size)
  POST   /api/analyze           multipart: csv (optional), chart (optional image), use_sample, symbol,
                                timeframe, capital, risk_pct, price
  GET    /api/analyses          history
  GET    /api/analyses/<id>     one saved analysis
  DELETE /api/analyses/<id>     delete
  POST   /api/ask               RAG Q&A over the knowledge base  {"question": "..."}
"""
import os
import uuid

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

from config import Config
from db import Database
from services import analyzer, indicators, llm
from services.image_analysis import analyze_chart_image
from services.rag import KnowledgeBase


def create_app(config=Config):
    app = Flask(__name__)
    app.config.from_object(config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db = Database(app.config["DATABASE_URL"])
    kb = KnowledgeBase(app.config["KNOWLEDGE_DIR"])

    def num(name, default, lo, hi):
        try:
            v = float(request.form.get(name, default))
        except (TypeError, ValueError):
            v = default
        return min(max(v, lo), hi)

    # ---------------- pages ----------------
    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        provider = "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "openai" if os.getenv("OPENAI_API_KEY") else "offline-fallback"
        return jsonify(status="ok", database=db.dialect, llm_provider=provider, knowledge_chunks=len(kb.chunks))

    # ---------------- analysis ----------------
    @app.post("/api/analyze")
    def analyze():
        symbol = (request.form.get("symbol") or "DEMO").strip().upper()[:30]
        timeframe = (request.form.get("timeframe") or "1D").strip()[:10]
        capital = num("capital", 10000, 100, 1e9)
        risk_pct = num("risk_pct", 1, 0.1, 5)
        price = request.form.get("price", type=float)

        df = None
        csv = request.files.get("csv")
        try:
            if request.form.get("use_sample") == "1":
                df = indicators.load_ohlc(app.config["SAMPLE_CSV"])
                if symbol == "DEMO":
                    symbol = "SAMPLE.NS"
            elif csv and csv.filename:
                if not csv.filename.lower().endswith(".csv"):
                    return jsonify(error="Price data must be a .csv file."), 400
                df = indicators.load_ohlc(csv.read())

            img_feat = None
            chart = request.files.get("chart")
            if chart and chart.filename:
                ext = chart.filename.rsplit(".", 1)[-1].lower()
                if ext not in app.config["ALLOWED_IMAGES"]:
                    return jsonify(error="Chart must be a PNG, JPG or WEBP image."), 400
                # file-management: store with a random name, keep the original name only as metadata
                saved = f"{uuid.uuid4().hex}.{ext}"
                path = os.path.join(app.config["UPLOAD_FOLDER"], saved)
                chart.save(path)
                try:
                    img_feat = analyze_chart_image(path)
                except Exception:
                    os.remove(path)
                    raise
                img_feat["file"] = saved
                img_feat["original_name"] = secure_filename(chart.filename)

            result = analyzer.analyze(df, img_feat, price, capital, risk_pct)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        except Exception as e:  # unreadable CSV / corrupt image etc.
            return jsonify(error=f"Could not process the input: {type(e).__name__}: {e}"), 400

        # ---- RAG: build a query from what the engine found, retrieve, then generate ----
        query = " ".join(result["reasons"]) + f" {result['signal']} stop-loss risk reward position sizing"
        chunks = kb.retrieve(query, k=4)
        report = llm.generate_report(result, symbol, timeframe, chunks)
        sources = [{"title": c["title"], "score": c["score"]} for c in chunks]

        payload = {"symbol": symbol, "timeframe": timeframe, "analysis": result, "report": report, "sources": sources}
        aid = db.insert_analysis(symbol, timeframe, result["signal"], result["confidence"], result["price"],
                                 result["source"], payload)
        payload["id"] = aid
        return jsonify(payload)

    # ---------------- history ----------------
    @app.get("/api/analyses")
    def history():
        return jsonify(db.list_analyses())

    @app.get("/api/analyses/<int:aid>")
    def one(aid):
        row = db.get_analysis(aid)
        if not row:
            return jsonify(error="Not found"), 404
        out = row["result"]
        out["id"] = aid
        return jsonify(out)

    @app.delete("/api/analyses/<int:aid>")
    def delete(aid):
        db.delete_analysis(aid)
        return jsonify(ok=True)

    # ---------------- RAG chat ----------------
    @app.post("/api/ask")
    def ask():
        q = ((request.get_json(silent=True) or {}).get("question") or "").strip()
        if len(q) < 3:
            return jsonify(error="Please type a question."), 400
        chunks = kb.retrieve(q, k=3)
        out = llm.answer_question(q, chunks)
        out["sources"] = [{"title": c["title"], "score": c["score"]} for c in chunks]
        return jsonify(out)

    @app.errorhandler(413)
    def too_big(_):
        return jsonify(error="File too large (max 8 MB)."), 413

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=True)
