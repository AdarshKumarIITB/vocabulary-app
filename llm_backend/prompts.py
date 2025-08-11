def get_word_generation_prompt(existing_words, known_words, unknown_words, theme=None):
    """
    Constructs detailed prompt for LLM to generate new vocabulary word
    Includes list of all existing words to avoid duplicates
    Provides known_words list to gauge user's vocabulary level
    Provides unknown_words list to understand learning progress
    If theme is specified, instructs to generate word within that theme
    Asks for response in specific JSON format with word, meanings, examples
    Instructs on appropriate difficulty based on known/unknown ratio
    Returns complete prompt string ready for LLM API call
    """
    
    # Convert word lists to readable strings
    existing_words_str = ", ".join(existing_words) if existing_words else "None"
    known_words_str = ", ".join(known_words) if known_words else "None"
    unknown_words_str = ", ".join(unknown_words) if unknown_words else "None"
    
    difficulty_instruction="Generate words of the same difficulty level that the user had to learn. Should be above the level of words user already knew."

    # Theme instruction if provided
    theme_instruction = f"\nThe word should be related to the theme: {theme}" if theme else ""
    
    prompt = f"""You are a vocabulary tutor helping a user learn new English words. Your task is to generate a **new** vocabulary word for the user to learn.

EXISTING WORDS (DO NOT REPEAT ANY OF THESE):
{existing_words_str}

WORDS THE USER ALREADY KNEW:
{known_words_str}

WORDS THE USER HAD TO LEARN:
{unknown_words_str}

DIFFICULTY GUIDANCE:
{difficulty_instruction}
{theme_instruction}

Generate a vocabulary word that:
1. Is NOT in the existing words list
2. Is appropriate for the user's current level
3. Is a real English word that would be useful to know
4. Is not overly obscure or archaic
5. Give meanings from trustable sources only

Respond ONLY with a JSON object in this exact format:
{{
    "word": "the_vocabulary_word",
    "meanings": [
        "First or most common meaning/definition of the word",
        "Further meanings/definitions if applicable"
    ],
    "examples": [
        "An example sentence using the word in context.",
        "Another example sentence showing different usage.",
        "Another example sentence illustrating word in different context.
    ]
}}

Strictly no markdown code block markers in JSON output.

Make sure the examples are clear and help illustrate the word's meaning."""
    
    return prompt


def get_tutor_response_prompt(thread_context, user_message, word):
    """
    Creates prompt for LLM to respond as vocabulary tutor
    Includes complete thread context for continuity
    Provides user's latest message for response
    Sets personality: helpful, encouraging, educational
    Instructs to stay on topic of vocabulary learning
    For off-topic messages, instructs to politely redirect
    Returns formatted prompt string
    """
    
    prompt = f"""You are a helpful vocabulary tutor engaged in a conversation about learning a new vocabulary word, "{word}". 

Here is the conversation history:
{thread_context}

The user just said:
{user_message}

As a vocabulary tutor, provide a helpful, encouraging and educational response. Consider:

1. If they're asking a question about the word, answer it clearly
2. If they're trying to use the word in a sentence, evaluate if it's correct and provide feedback
3. If they need more examples or clarification, provide them
4. If they seem confused, help clarify the meaning and usage
5. If they're going off-topic, gently redirect to vocabulary learning

Keep your response concise (2-3 sentences max), encouraging, and educational.
If the user successfully used the word correctly in a sentence, congratulate them.

Respond naturally as a tutor would, helping the user understand and learn the vocabulary word effectively.
Always end the response with a "Let me know if you have more questions. If you want a new word, just reply with a '1' "
"""


    return prompt

## Do we need this?
def get_system_prompt():
    """
    Returns base system prompt used across all LLM interactions
    Defines the assistant as a vocabulary tutor
    Sets tone: professional but friendly, educational
    Establishes boundaries: focus on vocabulary learning
    Used as consistent base for all LLM calls
    """
    
    return """You are an expert vocabulary tutor helping users expand their English vocabulary. Maintain an encouraging and educational tone. Keep conversations focused on vocabulary learning"""