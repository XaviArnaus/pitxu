from gemini_tool_agent.agent import Agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack
from typing import Optional
import asyncio

from google import genai
from google.genai import types

from pyxavi import Dictionary, Config
from pitxu.lib.abstract.pyxavi import PyXavi

# TEST MCP n.1
# NOT YET TRIED

# {
#   "mcpServers": {
#     "mcp_trivago_search": {
#       "url": "https://mcp.trivago.com/mcp"
#     }
#   }
# }

class TrivagoMCPServer(PyXavi):

    server_script_path: str = "https://mcp.trivago.com/mcp"
    session: Optional[ClientSession] = None
    exit: AsyncExitStack
    # agent=Agent(key=self._xparams.get("api_key"))
    tools: list = []

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(TrivagoMCPServer, self).init_pyxavi(config=config, params=params)
        self.session = None
        self.exit = AsyncExitStack()
        asyncio.run(self.connect_to_mcp_server())
    
    async def connect_to_mcp_server(self):
        self._xlog.debug("Connecting to Trivago's MCP Server...")

        is_python = self.server_script_path.endswith('.py')
        is_js = self.server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        cmd="python" if is_python else "node"
        server=await self.exit.enter_async_context(
            stdio_client(
                StdioServerParameters(
                    command=cmd,
                    args=[self.server_script_path],
                    env=None,
                )
            )
        )
        self.stdio,self.write=server
        self.session = await self.exit.enter_async_context(ClientSession(self.stdio, self.write))
        await self.session.initialize()
        response = await self.session.list_tools()
        tools = [{
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools
        ]

        self.tools=tools
        self._xlog.debug("\nConnected to server with tools:", [tool["name"] for tool in tools])
    
    def get_trivago_response_to_a_prompt(self, prompt: str) -> str:
        '''
        Gets a response from the Trivago MCP server related to the given prompt.

        Returns:
            The Gemini response from the Trivago MCP server as a JSON object.
        '''
        # Apparently the prompt always comes in English, so no need to translate it.
        # Still, looking at the logs, it's not always the case.
        self._xlog.debug(f"Getting Trivago MCP server response for prompt: [{prompt}] using language [{self._xparams.get('language')}]")
        instructions = self.get_prompt(self._xparams.get('language'))

        client = genai.Client(api_key=self._xparams.get("api_key"))
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=instructions,
                tools=self.tools
            )
        )

        self._xlog.debug(f"Trivago MCP Server response: {response.text}")
        return response.text
    
    def get_prompt(self, language: str) -> str:

        tools_description = {
            "ca": f"""
                - Nom: %s
                - Descripció: %s
                - Esquema d'Entrada: %s
                """,
            "es": f"""
                - Nombre: %s
                - Descripción: %s
                - Esquema de Entrada: %s
                """,
            "en-us": f"""
                - Name: %s
                - Description: %s
                - Input Schema: %s
                """,
            "de": f"""
                - Name: %s
                - Beschreibung: %s
                - Eingabeschema: %s
                """,
        }

        prompts = {
            "ca": f"""
                # Tasca per a Executar Eines
                
                ## Contexte
                Estàs analitzant una conversa per extreure els paràmetres per a una crida a una eina.
                
                ## Eines disponibles
                %s

                ## Conversa Prèvia: {self.history[-7:] if len(self.history) >= 7 else self.history}

                ## Instruccions
                1. Analitza acuradament la conversa anterior
                2. Extreu tots els paràmetres necessaris requerits per l'esquema d'entrada de l'eina
                3. Formateja els valors adequadament segons els seus tipus esperats
                4. No afegeixis cap paràmetre no especificat en l'esquema
                5. Si falta un paràmetre requerit a la conversa, utilitza un valor raonable per defecte o un marcador de posició

                ## Format de Resposta
                Respon NOMÉS amb un objecte JSON vàlid en aquest format:
                {{
                    "tool_name": "nom_de_l_eina",
                    "input": {{
                        "parameter1": "value1",
                        "parameter2": "value2",
                        ... 
                    }}
                }}
            """,
            "es": f"""
                # Tarea para Llamar a Herramientas

                ## Contexto
                Estás analizando una conversación para extraer parámetros para una llamada a una herramienta.

                ## Herramientas disponibles
                %s

                ## Conversación Previa: {self.history[-7:] if len(self.history) >= 7 else self.history}

                ## Instrucciones
                1. Analiza cuidadosamente la conversación anterior
                2. Extrae todos los parámetros necesarios requeridos por el esquema de entrada de la herramienta
                3. Formatea los valores adecuadamente según sus tipos esperados
                4. No añadas ningún parámetro no especificado en el esquema
                5. Si falta un parámetro requerido en la conversación, utiliza un valor razonable por defecto o un marcador de posición

                ## Formato de Respuesta
                Responde SÓLO con un objeto JSON válido en este formato:
                {{
                    "tool_name": "nombre_de_la_herramienta",
                    "input": {{
                        "parameter1": "value1",
                        "parameter2": "value2",
                        ... 
                    }}
                }}
            """,
            "en-us": f"""
                # Tool Calling Task
                
                ## Context
                You are analyzing a conversation to extract parameters for a tool call.
                
                ## Tools Available
                %s
                
                ## Previous Conversation: {self.history[-7:] if len(self.history) >= 7 else self.history}

                ## Instructions
                1. Carefully analyze the conversation above
                2. Extract all necessary parameters required by the tool's input schema
                3. Format values appropriately according to their expected types
                4. Do not add any parameters not specified in the schema
                5. If a required parameter is missing from the conversation, use a reasonable default or placeholder
                
                ## Response Format
                Respond ONLY with a valid JSON object in this exact format:
                {{
                    "tool_name": "tool_name",
                    "input": {{
                        "parameter1": "value1",
                        "parameter2": "value2",
                        ... 
                    }}
                }}
                """,
            "de": f"""
                # Toolaufruf-Aufgabe

                ## Kontext
                Sie analysieren ein Gespräch, um Parameter für einen Toolaufruf zu extrahieren

                ## Verfügbare Werkzeuge
                %s

                ## Vorheriges Gespräch: {self.history[-7:] if len(self.history) >= 7 else self.history}

                ## Anweisungen
                1. Analysieren Sie sorgfältig das obige Gespräch
                2. Extrahieren Sie alle notwendigen Parameter, die vom Eingabeschema des Tools benötigt werden
                3. Formatieren Sie die Werte entsprechend ihren erwarteten Typen
                4. Fügen Sie keine Parameter hinzu, die nicht im Schema angegeben sind
                5. Wenn ein erforderlicher Parameter im Gespräch fehlt, verwenden Sie einen vernünftigen Standardwert oder Platzhalter

                ## Antwortformat
                Antworten Sie NUR mit einem gültigen JSON-Objekt in diesem genauen Format:
                {{
                    "tool_name": "tool_name",
                    "input": {{
                        "parameter1": "value1",
                        "parameter2": "value2",
                        ... 
                    }}
                }}
                """
        }

        tools_info = "\n".join([tools_description[language] % (tool["name"], tool["description"], tool["input_schema"]) for tool in self.tools])
        prompt = prompts[language] % tools_info 
        return prompt
        