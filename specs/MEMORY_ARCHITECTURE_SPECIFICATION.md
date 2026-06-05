# Agent Memory Architecture Specification

**Version:** 1.0  
**Date:** June 2026  
**Purpose:** Comprehensive guide for how agents should access and save information in memory systems

---

## Table of Contents

1. [Overview](#overview)
2. [Memory System Components](#memory-system-components)
3. [Memory Types](#memory-types)
4. [Storage Architecture](#storage-architecture)
5. [Memory Access Patterns](#memory-access-patterns)
6. [Memory Saving Mechanisms](#memory-saving-mechanisms)
7. [Context Generation for LLM](#context-generation-for-llm)
8. [Implementation Guidelines](#implementation-guidelines)
9. [Best Practices](#best-practices)
10. [Examples](#examples)

---

## Overview

The Agent Memory Architecture is a multi-layered system designed to enable AI agents to maintain and leverage multiple types of memory for continuity, personalization, and knowledge accumulation. The system consists of **four distinct memory tiers**, each serving a specific purpose in agent cognition and decision-making.

### Key Objectives

- **Continuity**: Agents remember past interactions and context across sessions
- **Personalization**: Agents tailor responses based on user-specific information and preferences
- **Knowledge Accumulation**: Agents grow more capable by learning and retaining facts and procedures
- **Contextual Awareness**: Agents generate appropriate responses by leveraging relevant historical data
- **Efficiency**: Working memory maintains important context without overwhelming the system

---

## Memory System Components

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│           AI Agent with Memory System                    │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Working    │  │  Persistent  │  │   Search &   │  │
│  │   Memory     │  │   Storage    │  │  Retrieval   │  │
│  │  (RAM-based) │  │ (File-based) │  │   Engine     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│       │                  │                    │          │
│       └──────────────────┴────────────────────┘          │
│                    │                                      │
│           ┌────────▼────────┐                            │
│           │  Context        │                            │
│           │  Generator      │                            │
│           └────────┬────────┘                            │
│                    │                                      │
│           ┌────────▼────────┐                            │
│           │  LLM with       │                            │
│           │  Memory Context │                            │
│           └─────────────────┘                            │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

---

## Memory Types

### 1. Semantic Memory (Persistent Facts)

**Purpose**: Store factual information, knowledge, and concepts that transcend individual conversations.

#### Structure
```json
{
  "content": "String containing the fact or knowledge statement",
  "category": "Optional category for organization (e.g., 'programming', 'AI', 'history')",
  "timestamp": "ISO 8601 timestamp of when the fact was stored"
}
```

#### Storage
- **File**: `facts_semantic.json`
- **Format**: JSON Array of fact objects
- **Persistence**: Persistent across all sessions

#### Characteristics
- **Grows over time** as the agent learns new information
- **Immutable once stored** (facts don't change, though duplicates may exist)
- **Searchable** using keyword matching
- **Categorizable** for better organization and retrieval

#### Example Data
```json
[
  {
    "content": "I am an AI assistant with memory capabilities.",
    "category": null,
    "timestamp": "2025-04-02T12:47:06.065521"
  },
  {
    "content": "Python is a high-level programming language known for its readability.",
    "category": "programming",
    "timestamp": "2025-04-02T12:47:06.065892"
  },
  {
    "content": "Paulo knows Python very well.",
    "category": "user-profile",
    "timestamp": "2025-04-02T12:58:04.738241"
  }
]
```

---

### 2. Episodic Memory (Conversation History)

**Purpose**: Record specific interactions, conversations, and contextual events with timestamps.

#### Structure
```json
{
  "user_message": "The user's input message",
  "agent_response": "The agent's response to the user",
  "timestamp": "ISO 8601 timestamp of the conversation",
  "metadata": "Optional dictionary for additional context (e.g., intent, sentiment, session_id)"
}
```

#### Storage
- **File**: `conversations_episodic.json`
- **Format**: JSON Array of conversation objects
- **Persistence**: Persistent across all sessions
- **Growth**: Accumulates continuously; consider archival/pruning strategies for long-term systems

#### Characteristics
- **Time-bound** and chronologically ordered
- **Rich context** including both input and output
- **Queryable** by content and keywords
- **Retrievable by recency** for recent conversation context

#### Example Data
```json
[
  {
    "user_message": "Please tell me about python",
    "agent_response": "Python is a high-level, interpreted programming language...",
    "timestamp": "2025-04-02T12:47:51.073003",
    "metadata": {}
  },
  {
    "user_message": "who am I?",
    "agent_response": "You are Paulo! You've been interested in becoming a good programmer...",
    "timestamp": "2025-04-02T12:53:03.161445",
    "metadata": {"intent": "identity_query"}
  }
]
```

---

### 3. Procedural Memory (Workflows & Procedures)

**Purpose**: Store step-by-step procedures, workflows, and methods for accomplishing tasks.

#### Structure
```json
{
  "name": "Procedure identifier/title",
  "steps": ["Step 1", "Step 2", "Step 3", "..."],
  "description": "Optional description of what the procedure does",
  "timestamp": "ISO 8601 timestamp of when created",
  "usage_count": "Integer tracking how often this procedure was used"
}
```

#### Storage
- **File**: `procedures.json`
- **Format**: JSON Object (key: procedure name, value: procedure object)
- **Persistence**: Persistent across all sessions

#### Characteristics
- **Executable sequences** of actions or operations
- **Reusable** across multiple contexts
- **Updatable** (procedures can be refined over time)
- **Usage-tracked** to identify frequently used procedures
- **Described** for clarity and context

#### Example Data
```json
{
  "Create a simple AI agent with memory": {
    "name": "Create a simple AI agent with memory",
    "steps": [
      "Initialize memory storage (files, database, etc.)",
      "Create functions to add facts to semantic memory",
      "Create functions to store conversation history in episodic memory",
      "Create functions to retrieve relevant memory based on context",
      "Connect memory system to an LLM like GPT-4o-mini",
      "Implement a query function that includes memory context in prompts",
      "Add memory updating after each interaction"
    ],
    "description": "Steps to create a basic AI agent with memory capabilities",
    "timestamp": "2025-04-02T13:15:17.956544",
    "usage_count": 0
  }
}
```

---

### 4. Working Memory (Short-term Context)

**Purpose**: Maintain recent, high-importance information in RAM for immediate context without persistence overhead.

#### Structure
```json
{
  "content": "The working memory item content",
  "importance": "Float between 0.0 and 1.0 indicating priority",
  "timestamp": "ISO 8601 timestamp of when added"
}
```

#### Storage
- **Location**: In-memory (RAM)
- **Capacity**: Configurable limit (default: 10 items)
- **Persistence**: Lost when agent session ends
- **Eviction Policy**: When capacity exceeded, least important items removed

#### Characteristics
- **Fast access** (no disk I/O)
- **Limited capacity** to prevent memory bloat
- **Importance-weighted** for smart eviction
- **Ephemeral** by design
- **Updated continuously** during agent operation

#### Eviction Strategy
When working memory reaches capacity (default 10 items):
1. Sort items by importance and timestamp
2. Remove the least important item
3. Maintain importance-based ordering

---

## Storage Architecture

### Directory Structure

```
agent_memory/
├── facts_semantic.json          # Semantic memory store
├── conversations_episodic.json  # Episodic memory store
└── procedures.json              # Procedural memory store
```

### File Format Specifications

#### JSON Files (Semantic, Episodic, Procedural)

**Characteristics:**
- Human-readable format for debugging and analysis
- UTF-8 encoding
- 2-space indentation for readability
- ISO 8601 timestamps for all time-based fields

**Advantages:**
- Easy to inspect and audit
- Simple to parse and manipulate
- Platform-independent
- Suitable for small to medium-scale deployments

**Limitations:**
- Not ideal for very large-scale data (millions of records)
- No built-in querying capability
- Entire file must be loaded into memory for modifications

### Scalability Considerations

For production systems, consider:
- **Vector databases** (e.g., Pinecone, Weaviate) for semantic search at scale
- **SQL databases** (e.g., PostgreSQL) for episodic records with advanced querying
- **Document stores** (e.g., MongoDB) for flexible procedural memory
- **Archival strategy** for old conversations (e.g., move to separate storage after 1 year)

---

## Memory Access Patterns

### 1. Writing to Memory

#### Adding Facts (Semantic Memory)

```python
def add_fact(content: str, category: Optional[str] = None) -> None:
    """
    Add a fact to semantic memory.
    
    Args:
        content: The factual statement to store
        category: Optional categorization (e.g., 'programming', 'user-profile')
    """
    fact = {
        "content": content,
        "category": category,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    self.facts.append(fact)
    self._save_json(self.facts, self.facts_file)
```

**When to Use:**
- Store learned facts about users
- Save domain-specific knowledge
- Record important discoveries from conversations
- Build a knowledge base over time

**Example Usage:**
```python
memory.add_fact("Paulo knows Python very well.", category="user-profile")
memory.add_fact("Memory systems in AI are crucial for personalization.", category="AI")
```

#### Adding Conversations (Episodic Memory)

```python
def add_conversation(
    user_message: str,
    agent_response: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Add a conversation turn to episodic memory.
    
    Args:
        user_message: The user's input
        agent_response: The agent's generated response
        metadata: Optional dict with additional context (intent, sentiment, etc.)
    """
    conversation = {
        "user_message": user_message,
        "agent_response": agent_response,
        "timestamp": datetime.datetime.now().isoformat(),
        "metadata": metadata or {},
    }
    self.conversations.append(conversation)
    self._save_json(self.conversations, self.conversations_file)
    
    # Also update working memory
    self.add_to_working_memory(f"User: {user_message}", importance=1.0)
    self.add_to_working_memory(f"Agent: {agent_response}", importance=0.9)
```

**When to Use:**
- After every agent-user interaction
- Automatically called during `query()` method
- Should be paired with working memory updates

**Example Usage:**
```python
memory.add_conversation(
    user_message="What are the steps to become a good programmer?",
    agent_response="Here are some steps...",
    metadata={"intent": "career-advice", "session_id": "session_123"}
)
```

#### Adding Procedures (Procedural Memory)

```python
def add_procedure(
    name: str,
    steps: List[str],
    description: Optional[str] = None,
) -> None:
    """
    Add a procedure to procedural memory.
    
    Args:
        name: Identifier and title of the procedure
        steps: List of step descriptions
        description: Optional explanation of what the procedure does
    """
    procedure = {
        "name": name,
        "steps": steps,
        "description": description,
        "timestamp": datetime.datetime.now().isoformat(),
        "usage_count": 0,
    }
    self.procedures[name] = procedure
    self._save_json(self.procedures, self.procedures_file)
```

**When to Use:**
- Store multi-step processes or workflows
- Record how to perform complex tasks
- Document procedures the agent has learned
- Create reusable instruction templates

**Example Usage:**
```python
memory.add_procedure(
    name="How to run a Python script",
    steps=[
        "Open Command Line Interface",
        "Navigate to script directory using 'cd' command",
        "Execute with 'python script.py' or 'python3 script.py'",
    ],
    description="Steps to run a Python script on any OS"
)
```

#### Adding to Working Memory

```python
def add_to_working_memory(content: str, importance: float = 1.0) -> None:
    """
    Add an item to working memory with importance score.
    
    Args:
        content: The information to store temporarily
        importance: Priority score (0.0 to 1.0) for eviction decisions
    """
    item = {
        "content": content,
        "importance": importance,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    self.working_memory.append(item)
    
    # Evict least important if over capacity
    if len(self.working_memory) > self.working_memory_capacity:
        self.working_memory.sort(key=lambda x: (x["importance"], x["timestamp"]))
        self.working_memory = self.working_memory[1:]
```

**When to Use:**
- Store transient information during interactions
- Keep high-importance items readily accessible
- Temporary context that shouldn't be permanently stored
- Information that aids current conversation

**Example Usage:**
```python
memory.add_to_working_memory("User is asking about Python", importance=1.0)
memory.add_to_working_memory("Previous topic was career advice", importance=0.8)
```

---

### 2. Reading from Memory

#### Searching Facts (Semantic Memory)

```python
def search_facts(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Simple keyword search for facts.
    
    Args:
        query: Search query (space-separated keywords)
        limit: Maximum number of results to return
        
    Returns:
        List of matching fact objects, sorted by relevance
    """
    query_terms = query.lower().split()
    results = []
    
    for fact in self.facts:
        content = fact["content"].lower()
        # Score based on number of matching terms
        score = sum(1 for term in query_terms if term in content)
        if score > 0:
            results.append((fact, score))
    
    # Sort by score (descending)
    results.sort(key=lambda x: x[1], reverse=True)
    return [item[0] for item in results[:limit]]
```

**Search Algorithm:**
- Keyword matching (case-insensitive)
- Scoring based on term frequency
- Returns top N results by relevance

**When to Use:**
- Retrieve relevant facts for current question
- Build context for LLM prompts
- Fact-checking and knowledge verification
- User profile queries (e.g., "What does the user know?")

**Example Usage:**
```python
relevant_facts = memory.search_facts("Python knowledge", limit=5)
# Returns facts matching "Python" and "knowledge"
```

#### Searching Conversations (Episodic Memory)

```python
def search_conversations(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Simple keyword search for past conversations.
    
    Args:
        query: Search query (space-separated keywords)
        limit: Maximum number of results to return
        
    Returns:
        List of matching conversation objects, sorted by relevance
    """
    query_terms = query.lower().split()
    results = []
    
    for conv in self.conversations:
        text = f"{conv['user_message']} {conv['agent_response']}".lower()
        score = sum(1 for term in query_terms if term in text)
        if score > 0:
            results.append((conv, score))
    
    results.sort(key=lambda x: x[1], reverse=True)
    return [item[0] for item in results[:limit]]
```

**When to Use:**
- Find similar past interactions
- Retrieve relevant conversation examples
- Answer "Have we discussed this before?" queries
- Extract context for decision-making

**Example Usage:**
```python
past_discussions = memory.search_conversations("Germany travel", limit=3)
# Returns conversations mentioning Germany and travel
```

#### Getting Recent Conversations (Episodic Memory)

```python
def get_recent_conversations(count: int = 5) -> List[Dict[str, Any]]:
    """
    Get the most recent conversations.
    
    Args:
        count: Number of recent conversations to retrieve
        
    Returns:
        List of the most recent conversations
    """
    return (
        self.conversations[-count:]
        if len(self.conversations) >= count
        else self.conversations
    )
```

**When to Use:**
- Provide immediate context from last few interactions
- Identify conversation patterns
- Detect topic shifts or continuity
- Quick context for current query

**Example Usage:**
```python
recent = memory.get_recent_conversations(count=3)
# Returns last 3 conversations for context
```

#### Searching Procedures (Procedural Memory)

```python
def search_procedures(query: str, limit: int = 2) -> List[Dict[str, Any]]:
    """
    Search for procedures by keyword matching.
    
    Args:
        query: Search query
        limit: Maximum number of procedures to return
        
    Returns:
        List of matching procedures, sorted by usage frequency
    """
    query = query.lower()
    results = []
    
    for name, procedure in self.procedures.items():
        text = f"{name} {procedure.get('description', '')}".lower()
        if query in text:
            results.append(procedure)
    
    # Sort by usage count
    results.sort(key=lambda x: x.get("usage_count", 0), reverse=True)
    return results[:limit]
```

**When to Use:**
- Find relevant procedures for current task
- Retrieve step-by-step instructions
- Suggest automated workflows
- Recommend proven methods

**Example Usage:**
```python
procedures = memory.search_procedures("create agent", limit=2)
# Returns procedures about creating agents
```

---

## Memory Saving Mechanisms

### Automatic Saving

The memory system implements **atomic writes** for data consistency:

```python
def _save_json(data: Any, file_path: str) -> None:
    """Save data to a JSON file with atomic write."""
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)
```

**Saving Behavior:**
- Triggered automatically after each write operation
- Entire memory structure written to disk
- Synchronous (blocking) operation
- No transaction rollback available

### When Data is Saved

| Memory Type | Trigger | Frequency |
|-------------|---------|-----------|
| **Semantic** | `add_fact()` called | Per fact |
| **Episodic** | `add_conversation()` called | Per conversation |
| **Procedural** | `add_procedure()` called | Per procedure |
| **Working** | `add_to_working_memory()` called | Per item (RAM only) |

### Save Points in Agent Workflow

```
User Input
   ↓
Process Query (may update working memory)
   ↓
Generate Response with Memory Context
   ↓
save_to_episodic_memory(user_msg, response)
   ↓
Update fact base if new knowledge discovered (optional)
   ↓
Return Response
```

### Performance Considerations

**Current Approach:**
- Simple, reliable, human-readable
- Suitable for small to medium deployments
- I/O overhead acceptable for most applications

**Optimization Strategies for Scale:**
1. **Batch Saves**: Collect multiple writes, save once per N operations
2. **Async Saves**: Use background threads/async tasks
3. **Database Backend**: Replace JSON with SQL/NoSQL for transactional support
4. **Compression**: Compress old conversations in archive storage
5. **Indexing**: Build in-memory indexes for faster searches

---

## Context Generation for LLM

### Purpose

The `generate_context_for_llm()` method synthesizes relevant memory into a coherent context string that the LLM uses to inform its responses.

```python
def generate_context_for_llm(self, current_message: str) -> str:
    """
    Generate a context string for the LLM using relevant memory.
    
    Args:
        current_message: The user's current input
        
    Returns:
        Formatted context string combining all memory types
    """
    # Get working memory
    working_items = sorted(
        self.working_memory,
        key=lambda x: (x["importance"], x["timestamp"]),
        reverse=True,
    )
    working_memory_text = "\n".join(
        [f"- {item['content']}" for item in working_items]
    )

    # Get recent conversations
    recent = self.get_recent_conversations(count=3)
    recent_text = "\n".join(
        [
            f"User: {conv['user_message']}\nAgent: {conv['agent_response']}"
            for conv in recent
        ]
    )

    # Get relevant facts
    relevant_facts = self.search_facts(current_message)
    facts_text = "\n".join([f"- {fact['content']}" for fact in relevant_facts])

    # Get relevant procedures
    relevant_procedures = self.search_procedures(current_message)
    procedures_text = ""
    for proc in relevant_procedures:
        steps = "\n".join(
            [f"  {i+1}. {step}" for i, step in enumerate(proc["steps"])]
        )
        procedures_text += f"Procedure: {proc['name']}\n{steps}\n\n"

    # Combine into context
    context = f"""
### Current Context (Working Memory):
{working_memory_text}

### Recent Conversation History:
{recent_text}

### Relevant Facts from Memory:
{facts_text}

### Relevant Procedures:
{procedures_text}
"""
    return context.strip()
```

### Context Composition Strategy

The generated context includes four components in order of immediacy:

1. **Working Memory** (Most Recent & Important)
   - High-importance items first
   - Provides immediate context
   - Limited to current session

2. **Recent Conversations** (Recent Context)
   - Last 3 interactions
   - Shows conversation continuity
   - Helps maintain thread coherence

3. **Relevant Facts** (Domain Knowledge)
   - Facts matching current query keywords
   - Top 3 results by relevance
   - Provides factual grounding

4. **Relevant Procedures** (Instructional Context)
   - Procedures matching query
   - Complete step-by-step instructions
   - Guides complex task execution

### Integration with LLM

```python
def query(self, user_message: str) -> str:
    """Query with memory context."""
    # Generate memory context
    memory_context = self.memory.generate_context_for_llm(user_message)
    
    # Build message array with context
    messages = [
        {
            "role": "system",
            "content": "You are a helpful AI assistant with memory capabilities."
        },
        {
            "role": "system",
            "content": f"Context from memory:\n{memory_context}"
        },
        {
            "role": "user",
            "content": user_message
        },
    ]
    
    # Call LLM with context
    response = llm.complete(messages)
    
    # Save interaction
    self.memory.add_conversation(user_message, response)
    
    return response
```

### Context Window Optimization

**Considerations:**
- Total context length affects LLM token usage
- Balance between comprehensiveness and efficiency
- Trim older facts if context exceeds limits
- Prioritize working memory and recent conversations

**Tunable Parameters:**
```python
recent_conversations_count = 3  # Adjust for context depth
relevant_facts_limit = 3         # Adjust for knowledge relevance
procedures_limit = 2             # Adjust for task guidance
working_memory_capacity = 10     # Adjust for immediate context size
```

---

## Implementation Guidelines

### 1. Initialization

Every agent must initialize memory:

```python
from agent_with_memory import AgentMemory, OpenAIAgent

# Initialize memory system
memory = AgentMemory(storage_dir="./agent_memory")

# Or use agent directly
agent = OpenAIAgent(memory_dir="./agent_memory")
```

**Initialization Checklist:**
- [ ] Create storage directory
- [ ] Load existing JSON files or create new ones
- [ ] Initialize working memory (empty list)
- [ ] Verify file permissions for read/write

### 2. Processing User Input

Standard flow for handling user messages:

```python
def process_user_message(user_input: str) -> str:
    """Standard message processing workflow."""
    
    # Step 1: Check for special commands (optional)
    if user_input.lower().startswith("remember that"):
        fact = user_input[len("remember that "):].strip()
        memory.add_fact(fact)
        return f"I've learned that: {fact}"
    
    # Step 2: Generate context from memory
    context = memory.generate_context_for_llm(user_input)
    
    # Step 3: Build LLM prompt with context
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant."},
        {"role": "system", "content": f"Context:\n{context}"},
        {"role": "user", "content": user_input},
    ]
    
    # Step 4: Get LLM response
    response = llm.complete(messages)
    
    # Step 5: Save conversation to episodic memory
    memory.add_conversation(user_input, response)
    
    # Step 6: Extract and save any new facts (optional)
    # This requires NER or fact extraction model
    
    return response
```

### 3. Explicit Learning Commands

Support special commands for intentional learning:

```python
# Command: "remember that [fact]"
def learn_fact(user_input: str):
    if user_input.lower().startswith("remember that "):
        fact = user_input[len("remember that "):].strip()
        memory.add_fact(fact)
        return f"Understood. I'll remember: {fact}"

# Command: "learn procedure: [name] steps: [step1, step2, ...]"
def learn_procedure(user_input: str):
    # Parse procedure name and steps
    # Add to procedural memory
    memory.add_procedure(name, steps, description)
    return f"I've learned the procedure: {name}"
```

### 4. Search and Retrieval

Properly utilize search methods:

```python
# Query-driven search
query = "user mentioned programming experience"
facts = memory.search_facts(query, limit=5)

# Temporal search
recent = memory.get_recent_conversations(count=10)

# Keyword search
procedures = memory.search_procedures("create agent", limit=3)
```

---

## Best Practices

### 1. Fact Management

**Good Practices:**
- Store specific, factual statements
- Use consistent terminology
- Categorize facts for better organization
- Include source or reasoning when possible

**Example:**
```python
# Good
memory.add_fact("Paulo's skill level in Python is advanced.", category="user-profile")
memory.add_fact("The Brandenburg Gate is a famous landmark in Berlin.", category="geography")

# Less Effective
memory.add_fact("stuff about programming")
memory.add_fact("things to remember")
```

### 2. Conversation Recording

**Good Practices:**
- Always save user-agent pairs together
- Include metadata for query/filtering
- Preserve exact user wording
- Timestamp all interactions

**Example:**
```python
memory.add_conversation(
    user_message=user_input,  # Preserve original input
    agent_response=response,
    metadata={
        "intent": "career-advice",        # Label intent
        "category": "programming",         # Domain category
        "session_id": current_session_id,  # Track sessions
        "success": response_was_helpful    # Track success
    }
)
```

### 3. Procedure Documentation

**Good Practices:**
- Clear, actionable step names
- Complete but concise descriptions
- Logical ordering of steps
- Include prerequisites if applicable

**Example:**
```python
memory.add_procedure(
    name="Set up Python development environment",
    steps=[
        "Install Python 3.9 or later from python.org",
        "Verify installation: python --version",
        "Create virtual environment: python -m venv venv",
        "Activate virtual environment: source venv/bin/activate",
        "Install required packages: pip install -r requirements.txt",
    ],
    description="Complete setup process for Python development"
)
```

### 4. Working Memory Management

**Good Practices:**
- Assign importance scores thoughtfully
- High importance (0.9-1.0): Critical current context
- Medium importance (0.5-0.8): Supporting context
- Low importance (0.1-0.4): Background information

**Example:**
```python
# Critical context
memory.add_to_working_memory("User is debugging a Python error", importance=1.0)

# Supporting context
memory.add_to_working_memory("Previous topic was installation setup", importance=0.7)

# Background info
memory.add_to_working_memory("Conversation started 5 minutes ago", importance=0.3)
```

### 5. Search Optimization

**Tips for Better Search Results:**
- Use specific keywords relevant to the domain
- Search for multiple related terms
- Adjust limit parameter based on needs
- Fall back to recent conversations if search fails

**Example:**
```python
# Search strategy
def find_relevant_memory(user_query):
    # Try specific search
    facts = memory.search_facts(user_query, limit=3)
    
    # If no results, broaden search
    if not facts:
        keywords = extract_keywords(user_query)
        facts = memory.search_facts(" ".join(keywords), limit=5)
    
    # Add recent context if still needed
    if not facts:
        recent = memory.get_recent_conversations(count=3)
        return recent
    
    return facts
```

### 6. Memory Maintenance

**For Long-running Agents:**

```python
def maintain_memory():
    """Periodic memory maintenance."""
    
    # 1. Identify and merge duplicate facts
    deduplicate_facts()
    
    # 2. Archive old conversations (older than 1 year)
    archive_old_conversations(older_than_days=365)
    
    # 3. Update procedure usage statistics
    update_procedure_usage()
    
    # 4. Identify unused procedures (usage_count == 0 for 6 months)
    cleanup_unused_procedures()
    
    # 5. Generate memory statistics
    print_memory_stats()
```

### 7. Privacy and Security

**Important Considerations:**
- Mark sensitive facts (PII) for special handling
- Implement access controls if multi-user
- Encrypt storage if handling sensitive data
- Provide memory export/deletion options

**Example:**
```python
def add_sensitive_fact(content: str, sensitivity_level: str = "high"):
    """Add fact with sensitivity marking."""
    fact = {
        "content": content,
        "sensitivity": sensitivity_level,  # "low", "medium", "high"
        "timestamp": datetime.now().isoformat(),
        "encrypted": sensitivity_level == "high"
    }
    # Apply encryption if needed
    if fact["encrypted"]:
        fact["content"] = encrypt(content)
    
    self.facts.append(fact)
    self._save_json(self.facts, self.facts_file)
```

---

## Examples

### Example 1: Complete Agent Conversation Flow

```python
from agent_with_memory import OpenAIAgent

# Initialize agent with memory
agent = OpenAIAgent(memory_dir="./agent_memory")

# User asks a question
user_message = "What should I know about Germany?"
response = agent.query(user_message)

# Agent automatically:
# 1. Searches memory for relevant facts about Germany
# 2. Retrieves recent conversations for context
# 3. Generates comprehensive context
# 4. Queries LLM with context
# 5. Saves the conversation to episodic memory

print(response)
```

### Example 2: Teaching Agent New Facts

```python
# User teaches agent about themselves
agent.query("remember that my name is Paulo")
agent.query("remember that I'm very experienced with Python")
agent.query("remember that I'm interested in machine learning")

# Later, agent can use these facts
user_query = "Who am I?"
response = agent.query(user_query)
# Response will reference the learned facts about Paulo
```

### Example 3: Recording Procedures

```python
# Agent learns a new procedure
agent.memory.add_procedure(
    name="Deploy Python application to AWS Lambda",
    steps=[
        "Package application with dependencies using pip install -r requirements.txt -t .",
        "Create deployment package: zip -r deployment.zip . -x '*.pyc'",
        "Create Lambda function in AWS console or CLI",
        "Upload deployment.zip as function code",
        "Set environment variables if needed",
        "Test with sample events",
        "Monitor logs with CloudWatch"
    ],
    description="Steps to deploy a Python application to AWS Lambda"
)

# Later when asked about deployment, agent references this procedure
```

### Example 4: Memory Inspection

```python
from memory_visualization import MemoryVisualizer

visualizer = MemoryVisualizer(memory_dir="./agent_memory")

# View all semantic facts
visualizer.show_semantic_memory()

# View conversation history
visualizer.show_episodic_memory(limit=10)

# View stored procedures
visualizer.show_procedural_memory()
```

---

## Summary

The Agent Memory Architecture provides a structured, multi-layered approach to enabling AI agents to:

1. **Remember** facts, conversations, and procedures persistently
2. **Access** relevant information efficiently through keyword search
3. **Update** their knowledge base as they learn
4. **Contextualize** responses by synthesizing memory into comprehensive prompts
5. **Scale** from simple single-file storage to distributed database backends

By following this specification, developers can build AI agents with rich memory capabilities that provide personalized, contextually-aware, and continuously improving user experiences.

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | June 2026 | Initial specification document |

---

## References

- [raw_agent_with_memory](../../agents-with-memory/raw_agent_with_memory/) - Reference implementation
- [OpenAI API Documentation](https://platform.openai.com/docs/)
- [JSON Schema Standards](https://json-schema.org/)
