# Content Creation Pipeline MVP - Project Structure

```
content-pipeline/
├── app/                           # Main application package
│   ├── __init__.py
│   ├── main.py                    # FastAPI application entry point
│   ├── config.py                  # Configuration management
│   │
│   ├── agents/                    # AI Agents package
│   │   ├── __init__.py
│   │   ├── base_agent.py          # Abstract base class for all agents
│   │   ├── research_agent.py      # Research and information gathering
│   │   └── writer_agent.py        # Content creation and writing
│   │
│   ├── core/                      # Core business logic
│   │   ├── __init__.py
│   │   └── orchestrator.py        # Main pipeline coordinator
│   │
│   └── models/                    # Data models and schemas
│       ├── __init__.py
│       └── content.py             # Pydantic models and enums
│
├── tests/                         # Test suite (separate from main app)
│   ├── __init__.py
│   ├── conftest.py               # Test configuration and fixtures
│   ├── test_agents.py            # Tests for AI agents
│   └── test_orchestrator.py      # Tests for orchestrator
│
├── requirements.txt               # Python dependencies
├── .env.example                  # Environment variables template
├── README.md                     # Project documentation
├── demo.py                       # Demo script to test functionality
├── start.sh                      # Startup script
├── plan.md                       # Original project plan
└── project_structure.md          # This file
```

## Key Components

### 1. **FastAPI Application** (`app/main.py`)
- RESTful API endpoints for content creation
- Background task processing
- CORS middleware
- Error handling and validation

### 2. **Configuration Management** (`app/config.py`)
- Environment variable handling
- Settings validation
- Agent configuration

### 3. **AI Agents** (`app/agents/`)
- **BaseAgent**: Abstract class with common functionality
- **ResearchAgent**: Information gathering and source validation
- **WriterAgent**: Content creation and narrative structure

### 4. **Content Orchestrator** (`app/core/orchestrator.py`)
- Coordinates agent execution
- Manages pipeline workflow
- Quality assessment and scoring
- Task status tracking

### 5. **Data Models** (`app/models/content.py`)
- Pydantic models for type safety
- Enums for content types and statuses
- Request/response schemas

### 6. **Database Schema** (Cloudflare D1)
- `organizations`: User organizations
- `users`: System users
- `content_requests`: Content creation requests
- `content_pieces`: Generated content
- `agent_tasks`: Agent execution tracking
- `quality_assessments`: Quality metrics

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API information |
| GET | `/health` | Health check |
| POST | `/api/v1/content/create` | Create new content |
| GET | `/api/v1/content/{id}` | Get content by ID |
| GET | `/api/v1/content/{id}/status` | Get creation status |
| DELETE | `/api/v1/content/{id}` | Cancel content creation |
| GET | `/api/v1/content` | List all content |
| GET | `/api/v1/stats` | System statistics |

## Agent Workflow

```
Content Request → Research Agent → Writer Agent → Quality Assessment → Final Content
```

1. **Research Phase**: Gather information, validate sources
2. **Writing Phase**: Create structured content based on research
3. **Quality Assessment**: Calculate quality, SEO, and fact-check scores
4. **Finalization**: Combine all components into final deliverable

## Quality Metrics

- **Overall Quality**: Content length + research depth + structure
- **SEO Score**: Title optimization + meta description + headings + keywords
- **Fact-check Score**: Based on research confidence and source credibility
- **Research Depth**: Number and quality of sources used

## Testing Strategy

- **Unit Tests**: Individual agent functionality
- **Integration Tests**: Agent coordination and pipeline flow
- **Mock Testing**: External API calls (OpenAI, Wikipedia)
- **Fixtures**: Reusable test data and configurations

## Future Extensions

This MVP provides a solid foundation for adding:
- Additional agents (SEO, Editor, Fact-Checker, Visual)
- Advanced quality gates and human review
- User authentication and authorization
- Rate limiting and usage tracking
- Content templates and personalization
- Multi-language support
- Advanced analytics and reporting