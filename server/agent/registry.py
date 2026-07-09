"""
Tool Registry - Tool registration and schema management
"""

import inspect
from typing import Dict, Any, List, Callable
from dataclasses import dataclass

from sciagent_server.config import is_capability_enabled


@dataclass
class ToolSchema:
    """Schema definition for a tool"""
    name: str
    description: str
    parameters: Dict[str, Any]
    function: Callable


class ToolRegistry:
    """Registry for managing available tools and their schemas"""
    
    def __init__(self):
        self._tools: Dict[str, ToolSchema] = {}
        self._register_builtin_tools()
    
    def register_tool(self, name: str, description: str, function: Callable, parameters: Dict[str, Any] = None):
        """
        Register a tool with the registry
        
        Args:
            name: Tool name
            description: Tool description
            function: The function to call
            parameters: Parameter schema (optional)
        """
        if not is_capability_enabled(name):
            return

        if parameters is None:
            parameters = self._infer_parameters(function)

        schema = ToolSchema(
            name=name,
            description=description,
            parameters=parameters,
            function=function
        )
        
        self._tools[name] = schema
    
    def get_tool(self, name: str) -> ToolSchema:
        """Get a tool by name"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[Dict[str, str]]:
        """List all registered tools"""
        return [
            {
                "name": schema.name,
                "description": schema.description,
                "parameters": schema.parameters
            }
            for schema in self._tools.values()
        ]
    
    def execute_tool(self, name: str, **kwargs) -> Any:
        """Execute a tool with given parameters"""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found")
        
        return tool.function(**kwargs)
    
    def _infer_parameters(self, function: Callable) -> Dict[str, Any]:
        """Infer parameter schema from function signature"""
        sig = inspect.signature(function)
        parameters = {}
        
        for param_name, param in sig.parameters.items():
            param_info = {
                "type": param.annotation.__name__ if param.annotation != inspect.Parameter.empty else "str",
                "required": param.default == inspect.Parameter.empty
            }
            
            if param.default != inspect.Parameter.empty:
                param_info["default"] = param.default
                
            parameters[param_name] = param_info
        
        return parameters
    
    def _register_builtin_tools(self):
        """Register built-in tools"""
        # Import tools dynamically to avoid circular imports
        try:
            from tools.pubmed import fetch_pubmed
            self.register_tool(
                name="pubmed",
                description="Search PubMed for scientific articles",
                function=fetch_pubmed,
                parameters={
                    "query": {"type": "str", "required": True, "description": "Search query"}
                }
            )
        except ImportError:
            pass
        
        try:
            from tools.mygene import get_gene_summary
            self.register_tool(
                name="mygene",
                description="Get gene information from MyGene.info",
                function=get_gene_summary,
                parameters={
                    "symbol": {"type": "str", "required": True, "description": "Gene symbol"}
                }
            )
        except ImportError:
            pass
        
        try:
            from tools.uniprot import get_uniprot
            self.register_tool(
                name="uniprot",
                description="Get protein information from UniProt",
                function=get_uniprot,
                parameters={
                    "identifier": {"type": "str", "required": True, "description": "UniProt accession or symbol"}
                }
            )
        except ImportError:
            pass
        
        try:
            from tools.summarize import summarize_text
            self.register_tool(
                name="summarize",
                description="Summarize text using LLM",
                function=summarize_text,
                parameters={
                    "text": {"type": "str", "required": True, "description": "Text to summarize"}
                }
            )
        except ImportError:
            pass
        
        try:
            from tools.alphafold import get_alphafold
            self.register_tool(
                name="alphafold",
                description="Get AlphaFold protein structure information",
                function=get_alphafold,
                parameters={
                    "uniprot_id": {"type": "str", "required": True, "description": "UniProt ID"}
                }
            )
        except ImportError:
            pass
        
        try:
            from tools.clinvar import get_clinvar_variants
            self.register_tool(
                name="clinvar",
                description="Get genetic variants and clinical significance from ClinVar",
                function=get_clinvar_variants,
                parameters={
                    "gene_symbol": {"type": "str", "required": True, "description": "Gene symbol"}
                }
            )
        except ImportError:
            pass

        try:
            from tools.openalex import fetch_openalex
            self.register_tool(
                name="openalex",
                description="Search OpenAlex for scholarly works",
                function=fetch_openalex,
                parameters={
                    "query": {"type": "str", "required": True, "description": "Search query"}
                }
            )
        except ImportError:
            pass

        try:
            from tools.europepmc import fetch_europepmc
            self.register_tool(
                name="europepmc",
                description="Search Europe PMC for scientific articles",
                function=fetch_europepmc,
                parameters={
                    "query": {"type": "str", "required": True, "description": "Search query"}
                }
            )
        except ImportError:
            pass

        try:
            from tools.expression_atlas import search_expression_atlas
            self.register_tool(
                name="expression_atlas",
                description="Search EMBL-EBI Expression Atlas for gene expression experiments",
                function=search_expression_atlas,
                parameters={
                    "query": {"type": "str", "required": True, "description": "Search query"},
                    "species": {
                        "type": "str",
                        "required": False,
                        "description": "Optional species filter (e.g. Homo sapiens, human)",
                    },
                    "interpreted_query": {
                        "type": "dict",
                        "required": False,
                        "description": (
                            "Interpreted disease/tissue/assay facets for multi-strategy search"
                        ),
                    },
                },
            )
        except ImportError:
            pass

        try:
            from tools.geo_dataset_search import search_geo_datasets
            self.register_tool(
                name="geo_dataset_search",
                description="Search NCBI GEO for public omics datasets using grounded ontology concepts",
                function=search_geo_datasets,
                parameters={
                    "concept_mappings": {
                        "type": "list",
                        "required": True,
                        "description": "Grounded ontology concept mappings",
                    },
                    "max_results": {
                        "type": "int",
                        "required": False,
                        "description": (
                            "Maximum GEO records to retrieve and rank "
                            "(defaults to GEO_MAX_RESULTS env or 15)"
                        ),
                    },
                },
            )
        except ImportError:
            pass

        try:
            from tools.immport_dataset_search import search_immport_datasets
            self.register_tool(
                name="immport",
                description=(
                    "Search ImmPort shared immunology study metadata using grounded ontology concepts"
                ),
                function=search_immport_datasets,
                parameters={
                    "query": {"type": "str", "required": True, "description": "Search query"},
                    "interpreted_query": {
                        "type": "dict",
                        "required": False,
                        "description": (
                            "Interpreted disease/tissue/assay facets for multi-strategy search"
                        ),
                    },
                },
            )
        except ImportError:
            pass

        try:
            from tools.omicsdi_dataset_search import search_omicsdi_datasets
            self.register_tool(
                name="omicsdi",
                description=(
                    "Search OmicsDI for proteomics, metabolomics, and transcriptomics datasets "
                    "using grounded ontology concepts"
                ),
                function=search_omicsdi_datasets,
                parameters={
                    "query": {"type": "str", "required": True, "description": "Search query"},
                    "interpreted_query": {
                        "type": "dict",
                        "required": False,
                        "description": (
                            "Interpreted disease/tissue/assay facets for multi-strategy search"
                        ),
                    },
                },
            )
        except ImportError:
            pass

        try:
            from tools.proteomexchange_dataset_search import search_proteomexchange_datasets
            self.register_tool(
                name="proteomexchange",
                description=(
                    "Search ProteomeXchange for public proteomics datasets "
                    "using grounded ontology concepts"
                ),
                function=search_proteomexchange_datasets,
                parameters={
                    "query": {"type": "str", "required": True, "description": "Search query"},
                    "interpreted_query": {
                        "type": "dict",
                        "required": False,
                        "description": (
                            "Interpreted disease/tissue/assay facets for multi-strategy search"
                        ),
                    },
                },
            )
        except ImportError:
            pass

        try:
            from tools.vdjserver_dataset_search import search_vdjserver_datasets
            self.register_tool(
                name="vdjserver",
                description=(
                    "Search VDJServer for public immune repertoire (AIRR-seq) studies "
                    "using grounded ontology concepts"
                ),
                function=search_vdjserver_datasets,
                parameters={
                    "query": {"type": "str", "required": True, "description": "Search query"},
                    "interpreted_query": {
                        "type": "dict",
                        "required": False,
                        "description": (
                            "Interpreted disease/tissue/assay facets for multi-strategy search"
                        ),
                    },
                },
            )
        except ImportError:
            pass

        try:
            from tools.vivli_dataset_search import search_vivli_datasets
            self.register_tool(
                name="vivli",
                description=(
                    "Search Vivli and AccessClinicalData@NIAID clinical trial metadata "
                    "using grounded ontology concepts"
                ),
                function=search_vivli_datasets,
                parameters={
                    "query": {"type": "str", "required": True, "description": "Search query"},
                    "interpreted_query": {
                        "type": "dict",
                        "required": False,
                        "description": (
                            "Interpreted disease/tissue/assay facets for multi-strategy search"
                        ),
                    },
                },
            )
        except ImportError:
            pass
