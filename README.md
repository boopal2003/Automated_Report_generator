# Automated Report Generator (AI-Powered Workflow Summarizer)

> A smart, AI-powered reporting system that converts natural language questions into detailed workflow reports — complete with reasoning, provenance, and database traceability.

---

## Overview

**Automated Report Generator** is a Flask-based web application that leverages **Large Language Models (LLMs)** to understand workflow-related questions and generate structured reports from multiple database tables.  
It allows users to query complex workflow data in plain English and receive both **human-readable summaries** and **machine-parsable (JSON)** outputs — all driven by AI reasoning.

---

## Demo 

[Link](https://drive.google.com/file/d/1hs7BtPKkWfl3uwdD-2WRHKOcwWzPvlPK/view?usp=sharing)

![Report Generator UI](https://drive.google.com/file/d/1L4hR38aanSfqMQ6UBhsjBab-wKMqgsqn/view?usp=sharing)  
> _A clean, minimal interface for generating intelligent workflow summaries._

---

## Key Features

**Natural Language Querying**  
Ask questions like:  
> _“Show package counts by status for the last 7 days.”_  
and get instant workflow insights.

**AI-Powered Summarization**  
Understands schema, joins multiple tables intelligently, and generates summaries using a domain-aware system prompt.

**Traceability & Confidence Scoring**  
Each fact in the output includes provenance (table, field, ID) and confidence tags (High / Medium / Low).

**Dynamic Join Logic**  
Automatically expands joins (e.g., package → instance → workitem → participant) based on query intent.

**Human + Machine Friendly**  
Produces both **Markdown** and **JSON** outputs for end-users and downstream apps.

---

## Tech Stack

| Layer | Tools & Frameworks |
|-------|--------------------|
| **Backend** | Python 3.11, Flask, REST APIs |
| **AI / LLM** | OpenAI API / Custom LLM integration |
| **Frontend** | HTML5, Jinja2, CSS3 |
| **Database** | SQL (databases via connectors) |
| **Utilities** | Pandas, JSON, Logging |
| **Deployment** | Windows-based / Local development |

---

## Project Structure
report_gen/
│
├── app.py # Flask app entry point
├── config.py # Configuration loader
├── db.py # Database connector
├── extract_schema.py # Schema extraction logic
├── llm.py # LLM reasoning + summarization
│
├── prompts/
│ ├── system_prompt.example # Public-safe prompt
│ ├── sql_examples.txt # Example SQL patterns
│ └── schema.txt # Sample schema definitions
│
├── templates/
│ └── index.html # Web UI template
│
├── tests/
│ ├── test_api_key.py
│ ├── test_db_conn.py
│ └── init.py
│
├── utils/
│ ├── logger.py
│ └── sql_validator.py
│
├── requirements.txt
├── run_server.py
├── run_server.bat
└── README.md


## How It Works

**User Input**
You enter a natural-language query such as “Why is package X delayed?”

**Intent Detection**
The LLM identifies the anchor entity (package, instance, workitem, etc.) and determines which tables to join.

**Data Fetching**
The app dynamically builds SQL queries using schema info and extracts relevant data.

**Reasoning & Summarization**
The AI analyzes the joined data, detects anomalies, and composes a report with provenance.

**Dual Output**
You receive both a Markdown summary and a JSON block (detailed_summary) with structured fields.
