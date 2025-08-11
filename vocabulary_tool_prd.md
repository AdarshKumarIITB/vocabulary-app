# Vocabulary Enhancement Tool - Product Requirements Document

## Problem Statement
Create a mechanism to enhance English vocabulary through daily Slack interactions, targeting a single user who has low discipline and unlikely to use dedicated vocabulary apps.

## Solution Overview
An LLM-powered Slack bot that posts new vocabulary words daily in dedicated threads, engages users in learning interactions, and provides periodic quizzes based on performance analytics.

## Core User Flow
1. **Daily Word Posting**: System posts new word with definition, usage examples in new Slack thread
2. **Learning Interaction**: User indicates if they knew the word or learns it by using in sentence
3. **Immediate Progression**: If user knew word, system immediately posts new word in new thread
4. **Tutoring Support**: User can ask questions; system provides contextual tutoring
5. **Periodic Assessment**: Monthly quizzes or on-demand testing based on performance data

## Functional Requirements

### Word Management
- Generate new vocabulary words dynamically using a custom prompt (no predefined list)
- Avoid repeating words already in database
- Adapt difficulty based on user's demonstrated knowledge level
- Track user's prior knowledge vs. newly learned words

### Learning Interaction
- **Known Word Path**: User confirms prior knowledge → immediate new word in new thread
- **Learning Path**: User learns word → must demonstrate usage in original sentence
- **Validation**: LLM judges sentence correctness and provides feedback
- **Tutoring**: Answer follow-up questions with thread context

### Quiz System
- **Trigger**: Monthly automatic or user-requested
- **Selection Logic**: 90% unknown words, 10% previously known words
- **Performance-Based**: Test untested words or words with poor performance scores
- **Three Categories**:
  - Category 1: Multiple choice word meaning
  - Category 2: User writes meaning, LLM evaluates
  - Category 3: Contextual usage validation with explanation

### System Behavior
- **Dormancy**: No new threads for new words until user responds on last thread.
- **Thread Isolation**: Each new word gets dedicated thread
- **Channel Restriction**: Operates only in designated vocabulary channel

## Technical Architecture

### Components
1. **LLM Backend**: Core intelligence and data processing
2. **MCP Server**: Slack integration and webhook handling
3. **Database**: Single table for word tracking and performance

### Communication Flow
```
Slack → Webhook → MCP Server → HTTP → LLM Backend
LLM Backend → HTTP → MCP Server → Slack API → Slack
```

## Database Schema

### word_history Table
| Column | Type | Description |
|--------|------|-------------|
| word | VARCHAR(255) | The vocabulary word |
| prior_knowledge_flag | BOOLEAN | 1=user knew beforehand, 0=newly learned |
| quiz_category1_counter | INT | Number of Category 1 quiz questions asked till date |
| quiz_category_1_score | DECIMAL(5,2) | Weighted percentage score for Category 1 |
| quiz_category2_counter | INT | Number of Category 2 quiz questions asked till date |
| quiz_category_2_score | DECIMAL(5,2) | Weighted percentage score for Category 2 |
| quiz_category3_counter | INT | Number of Category 3 quiz questions asked till date |
| quiz_category_3_score | DECIMAL(5,2) | Weighted percentage score for Category 3 |

## Core Functions

### LLM Backend Functions

#### new_word_generator()
- **Input**: Database context of word and prior_knowledge_flag
- **Output**: New word with definition(s), multiple usage examples
- **Logic**: Avoid duplicates

#### LLM_as_a_judge()
- **Input**: User response, evaluation context, tolerance parameters
- **Output**: Boolean correctness + detailed feedback
- **Use Cases**: 
  - Sentence usage validation
  - Meaning explanation assessment

#### quiz_maker()
- **Input**: Performance data, word history
- **Output**: Structured quiz questions under each category based on performance algorithms
- **Logic**: 90/10 performance-based selection, category rotation

#### orchestrator()
- **Input**: User interactions from MCP server
- **Output**: Coordinated responses via appropriate functions
- **Logic**: Route interactions, maintain conversation context, trigger appropriate workflows

#### new_word_scheduler()
- **Input**: thread status
- **Output**: New word posting or dormancy state
- **Logic**: Daily posting if engaged

### MCP Server Functions

#### post_new_thread(message)
- Posts new vocabulary thread to designated channel
- Returns thread_id for tracking

#### reply_in_thread(thread_id, message)
- Responds within specific vocabulary thread
- Maintains conversation context

#### capture_user_response(thread_id, user_message)
- Captures user interactions from threads
- Forwards to LLM backend for processing

#### get_thread_history(thread_id)
- Retrieves complete thread conversation
- Provides context for tutoring responses

## Integration Specifications

### Slack Events
- **Thread Replies**: Primary interaction method
- **New Thread Creation**: For daily word posting
- **Channel Restriction**: Dedicated vocabulary channel only

### HTTP Transport
- Webhook endpoint for Slack events
- RESTful communication between MCP server and LLM backend
- Standard HTTP status codes for error handling

### LLM Provider
- **Service**: OpenAI API
- **Model**: To be specified based on performance requirements
- **Context Management**: Thread-aware prompt engineering

## Edge Cases & Constraints

### User Behavior
- Invalid sentence construction feedback
- Context-aware tutoring for follow-up questions

### System Constraints
- Single user system (no multi-user considerations)
- English language vocabulary only
- Slack platform dependency


## Future enhancements
- Pinned thread where user can update the themes on which it wants the vocabulary tutor to generate new words
- option to generate new word on demand and not only as per schedule
- add time decay in the formula that ranks which words to quiz on
 