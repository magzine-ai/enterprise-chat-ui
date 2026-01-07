"""
Google ADK (Agent Development Kit) Client for integrating with Google Generative AI.

This module provides integration with:
- Google Generative AI (Gemini API)
- Vertex AI (for enterprise deployments)
"""

import os
from typing import Dict, Any, Optional, List, AsyncIterator
from dataclasses import dataclass
import asyncio

# Google Generative AI
try:
    import google.generativeai as genai
    from google.generativeai.types import GenerateContentResponse
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    GOOGLE_GENAI_AVAILABLE = False
    print("⚠️ google-generativeai not available. Install: pip install google-generativeai")

# Vertex AI
try:
    from google.cloud import aiplatform
    from google.cloud.aiplatform.gapic.schema import predict
    VERTEX_AI_AVAILABLE = True
except ImportError:
    VERTEX_AI_AVAILABLE = False
    print("⚠️ google-cloud-aiplatform not available. Install: pip install google-cloud-aiplatform")

# LangChain Google GenAI
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain.schema import HumanMessage, AIMessage, SystemMessage
    LANGCHAIN_GOOGLE_AVAILABLE = True
except ImportError:
    LANGCHAIN_GOOGLE_AVAILABLE = False
    print("⚠️ langchain-google-genai not available. Install: pip install langchain-google-genai")


@dataclass
class GoogleADKConfig:
    """Configuration for Google ADK client."""
    api_key: Optional[str] = None
    model_name: str = "gemini-pro"
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.95
    top_k: int = 40
    use_vertex_ai: bool = False
    project_id: Optional[str] = None
    location: str = "us-central1"
    credentials_path: Optional[str] = None


class GoogleADKClient:
    """Client for Google ADK (Generative AI and Vertex AI)."""
    
    def __init__(self, config: Optional[GoogleADKConfig] = None):
        """
        Initialize Google ADK client.
        
        Args:
            config: Configuration for Google ADK
        """
        self.config = config or GoogleADKConfig()
        
        # Load API key from environment if not provided
        if not self.config.api_key:
            self.config.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        # Initialize based on configuration
        self.genai_model = None
        self.langchain_model = None
        self.vertex_ai_initialized = False
        
        self._initialize()
    
    def _initialize(self):
        """Initialize Google ADK clients."""
        if self.config.use_vertex_ai and VERTEX_AI_AVAILABLE:
            self._initialize_vertex_ai()
        elif GOOGLE_GENAI_AVAILABLE and self.config.api_key:
            self._initialize_generative_ai()
        elif LANGCHAIN_GOOGLE_AVAILABLE and self.config.api_key:
            self._initialize_langchain()
        else:
            print("⚠️ Google ADK not properly configured. Please set GOOGLE_API_KEY or configure Vertex AI.")
    
    def _initialize_generative_ai(self):
        """Initialize Google Generative AI client."""
        if not GOOGLE_GENAI_AVAILABLE:
            return
        
        try:
            genai.configure(api_key=self.config.api_key)
            self.genai_model = genai.GenerativeModel(self.config.model_name)
            print(f"✅ Google Generative AI initialized with model: {self.config.model_name}")
        except Exception as e:
            print(f"⚠️ Failed to initialize Google Generative AI: {e}")
    
    def _initialize_langchain(self):
        """Initialize LangChain Google GenAI client."""
        if not LANGCHAIN_GOOGLE_AVAILABLE:
            return
        
        try:
            self.langchain_model = ChatGoogleGenerativeAI(
                model=self.config.model_name,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                google_api_key=self.config.api_key
            )
            print(f"✅ LangChain Google GenAI initialized with model: {self.config.model_name}")
        except Exception as e:
            print(f"⚠️ Failed to initialize LangChain Google GenAI: {e}")
    
    def _initialize_vertex_ai(self):
        """Initialize Vertex AI client."""
        if not VERTEX_AI_AVAILABLE:
            return
        
        try:
            if self.config.credentials_path:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.config.credentials_path
            
            if self.config.project_id:
                aiplatform.init(
                    project=self.config.project_id,
                    location=self.config.location
                )
                self.vertex_ai_initialized = True
                print(f"✅ Vertex AI initialized: project={self.config.project_id}, location={self.config.location}")
        except Exception as e:
            print(f"⚠️ Failed to initialize Vertex AI: {e}")
    
    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
        stream: bool = False
    ) -> Any:
        """
        Generate text using Google ADK.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt/instructions
            context: Conversation context (list of {"role": "user/assistant", "content": "..."})
            stream: Whether to stream the response
            
        Returns:
            Generated text or async iterator for streaming
        """
        if self.langchain_model:
            return await self._generate_with_langchain(prompt, system_prompt, context, stream)
        elif self.genai_model:
            return await self._generate_with_genai(prompt, system_prompt, context, stream)
        elif self.vertex_ai_initialized:
            return await self._generate_with_vertex_ai(prompt, system_prompt, context, stream)
        else:
            raise RuntimeError("Google ADK not properly initialized")
    
    async def _generate_with_genai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
        stream: bool = False
    ) -> Any:
        """Generate text using Google Generative AI SDK."""
        if not self.genai_model:
            raise RuntimeError("Generative AI model not initialized")
        
        # Build full prompt
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        
        # Add context if provided
        if context:
            context_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in context])
            full_prompt = f"{context_text}\n\n{full_prompt}"
        
        # Configure generation parameters
        generation_config = genai.types.GenerationConfig(
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
            top_p=self.config.top_p,
            top_k=self.config.top_k
        )
        
        if stream:
            # Return async iterator for streaming
            async def stream_generator():
                try:
                    response = await asyncio.to_thread(
                        self.genai_model.generate_content,
                        full_prompt,
                        generation_config=generation_config,
                        stream=True
                    )
                    for chunk in response:
                        if hasattr(chunk, 'text') and chunk.text:
                            yield chunk.text
                except Exception as e:
                    raise RuntimeError(f"Error streaming from Generative AI: {e}")
            return stream_generator()
        else:
            # Generate synchronously (run in executor)
            response = await asyncio.to_thread(
                self.genai_model.generate_content,
                full_prompt,
                generation_config=generation_config
            )
            return response.text
    
    async def _generate_with_langchain(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
        stream: bool = False
    ) -> Any:
        """Generate text using LangChain Google GenAI."""
        if not self.langchain_model:
            raise RuntimeError("LangChain model not initialized")
        
        # Build messages
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        
        # Add context
        if context:
            for msg in context:
                if msg['role'] == 'user':
                    messages.append(HumanMessage(content=msg['content']))
                elif msg['role'] == 'assistant':
                    messages.append(AIMessage(content=msg['content']))
        
        # Add current prompt
        messages.append(HumanMessage(content=prompt))
        
        if stream:
            # Stream response
            async def stream_generator():
                async for chunk in self.langchain_model.astream(messages):
                    if hasattr(chunk, 'content'):
                        yield chunk.content
                    else:
                        yield str(chunk)
            return stream_generator()
        else:
            # Generate response
            response = await self.langchain_model.ainvoke(messages)
            return response.content if hasattr(response, 'content') else str(response)
    
    async def _generate_with_vertex_ai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
        stream: bool = False
    ) -> Any:
        """Generate text using Vertex AI."""
        # Vertex AI implementation would go here
        # This is a placeholder - actual implementation depends on Vertex AI API
        raise NotImplementedError("Vertex AI generation not yet implemented")
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        stream: bool = False
    ) -> Any:
        """
        Chat interface for Google ADK.
        
        Args:
            messages: List of messages with "role" and "content"
            system_prompt: System prompt/instructions
            stream: Whether to stream the response
            
        Returns:
            Response text or async iterator
        """
        # Extract last user message
        user_messages = [msg for msg in messages if msg.get('role') == 'user']
        if not user_messages:
            raise ValueError("No user messages found")
        
        prompt = user_messages[-1]['content']
        context = messages[:-1] if len(messages) > 1 else None
        
        return await self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            context=context,
            stream=stream
        )
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using Google ADK.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        # Placeholder - actual implementation depends on embedding model
        # Google Generative AI doesn't have a direct embedding API in the same way
        # This would typically use Vertex AI's text embedding model
        raise NotImplementedError("Embedding generation not yet implemented")
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model."""
        return {
            "model_name": self.config.model_name,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "use_vertex_ai": self.config.use_vertex_ai,
            "initialized": bool(self.genai_model or self.langchain_model or self.vertex_ai_initialized)
        }

