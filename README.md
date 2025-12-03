# Example LLM Application

This application uses Azure Open AI API for LLM and HuggingFace embeddings for document vectorization.

## Configuration

Create a `.env` file in the project root with your DeepSeek API key:

```bash
AZURE_OPENAI_API_KEY="********************"
AZURE_OPENAI_ENDPOINT=https://ai-proxy.lab.epam.com
OPENAI_API_VERSION=2025-04-01-preview
DATABASE_URI=postgresql://postgres:admin@localhost:5432/mydb

# students-project-13

This repository provides a Streamlit UI that translates natural-language queries into safe, read-only SQL statements targeting a `students` table. It uses Azure OpenAI with Function Calling for intelligent SQL generation based on business-meaningful schema metadata.

## Features

- 🤖 **LLM-Powered**: Uses Azure OpenAI GPT-4o with Function Calling
- 📊 **Business Metadata**: Maintains schema metadata table with business descriptions in Chinese
- 🔒 **Safe Queries**: Only allows SELECT operations with parameterized queries
- 🌐 **Bilingual**: Supports both English and Chinese prompts
- 📈 **Smart Functions**: Automatic selection between count and query operations

## Configuration

Create a `.env` file in the project root with the following variables:

```bash
# Database connection (PostgreSQL recommended)
DATABASE_URI="postgresql://<user>:<pass>@<host>:<port>/<db>"

# Azure OpenAI Configuration (Required)
AZURE_OPENAI_API_KEY="your-api-key"
AZURE_OPENAI_ENDPOINT="https://ai-proxy.lab.epam.com"
OPENAI_API_VERSION="2025-04-01-preview"
MODEL="gpt-4o"

# Development: opt into sqlite fallback (not recommended for production)
ALLOW_SQLITE_FALLBACK=0
```

## Setup

### 1. Install Dependencies

```bash
# Using virtual environment
source .venv/bin/activate
pip install -r requirements.txt

# Or using conda
conda activate myenv
pip install -r requirements.txt
```

### 2. Initialize Schema Metadata Table

**Important**: Before first use, initialize the schema metadata table:

```bash
python init_schema_metadata.py
```

This creates the `schema_metadata` table and populates it with business descriptions for the `students` table.

**What it does:**
- Creates `schema_metadata` table with business names and descriptions
- Adds metadata for students table (学生表) and its columns
- Enables LLM to understand Chinese business terms like "入学日期" → `enroll_date`

See [SCHEMA_METADATA.md](SCHEMA_METADATA.md) for detailed documentation.

## Run Application

Start the Streamlit app:

```bash
# Standard mode
streamlit run main.py

# Headless mode (for servers)
python -m streamlit run main.py --server.port 8501 --server.headless true
```

## How It Works

### Traditional Approach (Without Metadata)
```
User: "有多少学生？" 
→ LLM sees technical schema: id, name, enroll_date
→ May not understand Chinese business terms
```

### Enhanced Approach (With Metadata) ✨
```
User: "有多少2020年后入学的学生？"
  ↓
Query schema_metadata table
  ↓
LLM receives:
  表名: students (学生表)
  字段: enroll_date (入学日期 - 学生入学的日期)
  ↓
LLM understands: "入学" → enroll_date
  ↓
Generates: count_students(enroll_after_year=2020)
  ↓
Executes SQL & returns natural language response
```

## Schema Metadata

The `schema_metadata` table stores business-meaningful descriptions:

| Field | Description | Example |
|-------|-------------|---------|
| table_name | Table name | `students` |
| column_name | Column name | `enroll_date` |
| business_name | Business name (Chinese) | `入学日期` |
| business_description | Business description | `学生入学的日期` |
| data_type | Data type | `DATE` |
| sample_values | Example values | `["2020-09-01", "2021-09-01"]` |

### Add New Tables/Fields

```sql
-- Add table description
INSERT INTO schema_metadata (table_name, column_name, business_name, business_description)
VALUES ('courses', NULL, '课程表', '存储所有课程信息');

-- Add column description
INSERT INTO schema_metadata 
(table_name, column_name, business_name, business_description, data_type, sample_values)
VALUES 
('courses', 'course_name', '课程名称', '课程的完整名称', 'VARCHAR', '["数学", "英语"]');
```

See [SCHEMA_METADATA.md](SCHEMA_METADATA.md) for complete guide.

## Example Queries

### English
- "How many students enrolled after 2020?"
- "List all students"
- "Show me students from 2023"

### Chinese
- "有多少学生在2020年后入学？"
- "列出所有学生"
- "显示2023年入学的学生"

## Architecture

The system uses a two-phase LLM workflow:

1. **Planning Phase**: LLM analyzes the prompt with business metadata and selects appropriate function tool
   - `count_students()`: For "how many", "count" queries
   - `query_students()`: For "list", "show" queries

2. **Response Phase**: LLM generates natural language response based on query results

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

## Local Development (SQLite Fallback)

For quick local testing without PostgreSQL:

```bash
export ALLOW_SQLITE_FALLBACK=1
unset DATABASE_URI
streamlit run main.py
```

**Note**: SQLite fallback is for development only. The `schema_metadata` table may not work with SQLite.

## Testing

Test the metadata functionality:

```bash
# Test metadata query and formatting
python test_metadata.py

# Verify initialization
python init_schema_metadata.py
```

## Safety Features

- ✅ Only SELECT queries allowed
- ✅ Parameterized queries (SQL injection protection)
- ✅ Read-only database operations
- ✅ Function tools with strict parameter validation
- ✅ Automatic fallback to technical schema if metadata unavailable

## Troubleshooting

### Conda Activation Issues
```bash
CONDA_BASE=$(conda info --base)
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate myenv
```

### Schema Metadata Not Working
1. Check if table exists: `SELECT * FROM schema_metadata LIMIT 1;`
2. Re-run initialization: `python init_schema_metadata.py`
3. Check logs for warnings about metadata query failures

### LLM Not Understanding Chinese Terms
- Verify metadata table has Chinese business descriptions
- Check that `get_schema_metadata()` returns data
- Review system prompt in Streamlit UI

## Project Structure

```
students-project-13/
├── main.py                      # Streamlit UI
├── query_sql.py                 # Core logic with metadata support
├── init_schema_metadata.py      # Metadata initialization script
├── test_metadata.py             # Testing script
├── schema_metadata.sql          # SQL schema definition
├── SCHEMA_METADATA.md           # Metadata documentation
├── ARCHITECTURE.md              # System architecture
└── requirements.txt             # Python dependencies
```

## Contributing

1. Create a new branch from `main`
2. Make your changes
3. Test thoroughly (especially metadata queries)
4. Open a Merge Request

---

For more information:
- [Schema Metadata Guide](SCHEMA_METADATA.md)
- [Architecture Documentation](ARCHITECTURE.md)

