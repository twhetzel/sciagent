"""
Agent Orchestrator - Main agent loop: plan → act → observe → synthesize
"""

import json
import re
from typing import List, Dict, Any, Optional
from .registry import ToolRegistry
from .tracing import TraceCollector
from .prompts import SystemPrompts


class AgentOrchestrator:
    """Main orchestrator that manages the agent's plan-act-observe-synthesize loop"""
    
    def __init__(self):
        self.registry = ToolRegistry()
        self.tracer = TraceCollector()
        self.prompts = SystemPrompts()
        self.max_iterations = 5
        
    def run(
        self,
        query: str,
        *,
        search_options=None,
    ) -> tuple[str, List[Dict], Dict[str, Any] | None]:
        """
        Main entry point for the agent

        Args:
            query: User's question or request
            search_options: Optional dataset discovery retrieval options

        Returns:
            tuple: (final_response, execution_traces, optional dataset_search payload)
        """
        from domain.query_interpretation import is_dataset_discovery_query

        if is_dataset_discovery_query(query):
            repositories = self._resolve_dataset_repositories()
            if repositories:
                return self._run_dataset_discovery(
                    query,
                    repositories=repositories,
                    search_options=search_options,
                )

        self.tracer.start_trace("agent_run", {"query": query})
        
        try:
            # Step 1: Plan
            plan = self._filter_planned_tools(self._plan(query))
            self.tracer.log_step("plan", {"plan": plan})
            
            # Step 2-4: Act-Observe-Synthesize loop
            results = []
            for iteration in range(self.max_iterations):
                self.tracer.log_step("iteration", {"iteration": iteration + 1})
                
                # Act: Execute planned actions
                action_results = self._act(plan, iteration)
                results.extend(action_results)
                
                # Observe: Analyze results
                observations = self._observe(action_results)
                
                # Synthesize: Update plan based on observations
                updated_plan = self._synthesize(plan, observations, query)
                
                # Check if we have enough information
                if self._is_complete(updated_plan, observations):
                    break
                    
                plan = updated_plan
            
            # Ontology normalization (non-blocking — failures must not abort the query)
            results, normalize_trace = self._normalize_results(results)
            self.tracer.log_step("normalize", normalize_trace)

            # Final synthesis
            final_response = self._final_synthesis(results, query)
            
            self.tracer.end_trace("agent_run", {"final_response": final_response})
            return final_response, self.tracer.get_traces(), None
            
        except Exception as e:
            self.tracer.log_error("agent_run", str(e))
            return f"Error: {str(e)}", self.tracer.get_traces(), None

    def _resolve_dataset_repositories(self) -> list[str]:
        """Return enabled dataset repositories from the central registry (merge priority order)."""
        from domain.dataset_repository_registry import resolve_enabled_dataset_repositories

        return resolve_enabled_dataset_repositories(self.registry)

    def _run_dataset_discovery(
        self,
        query: str,
        *,
        repositories: list[str],
        search_options=None,
    ) -> tuple[str, List[Dict], Dict[str, Any]]:
        """Run the ontology-grounded dataset discovery vertical with explicit trace steps."""
        from agent import dataset_discovery as pipeline
        from domain.dataset_search import DatasetSearchOptions

        if search_options is None:
            from sciagent_server.config import resolve_dataset_search_options

            search_options = resolve_dataset_search_options(None)
        elif not isinstance(search_options, DatasetSearchOptions):
            from sciagent_server.config import resolve_dataset_search_options

            payload = (
                search_options.model_dump()
                if hasattr(search_options, "model_dump")
                else dict(search_options)
            )
            search_options = resolve_dataset_search_options(payload)

        repository_label = (
            repositories[0]
            if len(repositories) == 1
            else " + ".join(repositories)
        )

        self.tracer.start_trace(
            "agent_run",
            {
                "query": query,
                "mode": "dataset_discovery",
                "repository": repository_label,
                "repositories": repositories,
            },
        )

        try:
            interpreted, llm_trace = pipeline.interpret_query_pipeline(query)
            self.tracer.log_step(
                "interpret_query",
                {
                    "label": "Interpret Query",
                    "description": "Extract disease, tissue, assay, and organism facets from the query",
                    "interpreted_query": interpreted.model_dump(),
                },
            )
            if llm_trace is not None:
                self.tracer.log_step(
                    "interpret_llm",
                    {
                        "label": "Interpret Query (LLM fallback)",
                        "description": (
                            "Fill missing facets using LLM extraction validated through "
                            "ontology grounding when ANTHROPIC_API_KEY is set"
                        ),
                        **llm_trace,
                    },
                )

            concept_mappings = pipeline.ground_query(interpreted)
            self.tracer.log_step(
                "ground_query",
                {
                    "label": "Ground Query",
                    "description": "Map requested facets to ontology concepts via OLS/BioPortal with curated fallback",
                    "concept_mappings": [m.model_dump() for m in concept_mappings],
                    "mapping_count": len(concept_mappings),
                },
            )

            from domain.dataset_repository_registry import filter_repositories_for_interpreted_query

            repositories, skipped_repositories = filter_repositories_for_interpreted_query(
                repositories,
                interpreted,
                query=query,
            )
            if not repositories:
                raise ValueError(
                    "No dataset repositories remain for this query after applying assay filters. "
                    "Enable OmicsDI for metabolomics queries."
                )

            search_result = (
                pipeline.search_repositories(
                    repositories,
                    concept_mappings,
                    query=query,
                    interpreted_query=interpreted,
                    include_text_broad=search_options.include_text_broad,
                )
                if len(repositories) > 1
                else pipeline.search_repository(
                    repositories[0],
                    concept_mappings,
                    query=query,
                    interpreted_query=interpreted,
                    include_text_broad=search_options.include_text_broad,
                )
            )
            self.tracer.log_step(
                "search_repository",
                {
                    "label": "Search Repository",
                    "description": (
                        "Run multi-strategy search across enabled repositories "
                        "using grounded labels and synonyms"
                        if len(repositories) > 1
                        else f"Run multi-strategy {repositories[0]} search using grounded labels and synonyms"
                    ),
                    "repositories": repositories,
                    "skipped_repositories": skipped_repositories,
                    "repository": search_result.get("repository", repository_label),
                    "search_term": search_result.get("search_term", ""),
                    "search_strategies": search_result.get("search_strategies", []),
                    "total_found": search_result.get("total_found", 0),
                    "primary_total_found": search_result.get("primary_total_found"),
                    "max_results": search_result.get("max_results"),
                    "has_more": search_result.get("has_more", False),
                    "record_count": len(search_result.get("records", [])),
                    "source": search_result.get("source", repository_label),
                    "error": search_result.get("error"),
                },
            )

            records = search_result.get("records", [])
            candidates = (
                pipeline.normalize_merged_records(records)
                if len(repositories) > 1
                else pipeline.normalize_records(repositories[0], records)
            )
            self.tracer.log_step(
                "normalize_records",
                {
                    "label": "Normalize Records",
                    "description": (
                        "Convert repository API responses into shared DatasetCandidate records"
                        if len(repositories) > 1
                        else f"Convert {repositories[0]} API responses into shared DatasetCandidate records"
                    ),
                    "repositories": repositories,
                    "repository": search_result.get("repository", repository_label),
                    "input_records": len(records),
                    "candidate_count": len(candidates),
                },
            )

            annotated = pipeline.annotate_evidence(candidates, concept_mappings)
            evidence_snippet_count = sum(len(c.evidence_snippets) for c in annotated)
            self.tracer.log_step(
                "annotate_evidence",
                {
                    "label": "Annotate Evidence",
                    "description": "Identify metadata fields that support facet matches and collect evidence snippets",
                    "candidate_count": len(annotated),
                    "evidence_snippet_count": evidence_snippet_count,
                    "warning_count": sum(len(c.metadata_warnings) for c in annotated),
                },
            )

            ranked = pipeline.rank_results(annotated, concept_mappings)
            ranked = pipeline.discover_access(ranked)
            self.tracer.log_step(
                "rank_results",
                {
                    "label": "Rank Results",
                    "description": "Score candidates by evidence coverage; do not inherit requested facets without evidence",
                    "candidate_count": len(ranked),
                    "full_matches": sum(1 for c in ranked if c.match_status == "full"),
                    "full_with_warnings_matches": sum(
                        1 for c in ranked if c.match_status == "full_with_warnings"
                    ),
                    "partial_matches": sum(1 for c in ranked if c.match_status == "partial"),
                    "ambiguous_or_mixed_matches": sum(
                        1 for c in ranked if c.match_status == "ambiguous_or_mixed"
                    ),
                    "top_accessions": [c.accession for c in ranked[:5]],
                },
            )

            from domain.dataset_search import DatasetSearchCursor, DatasetSearchResult

            result = DatasetSearchResult(
                query=query,
                interpreted_query=interpreted,
                concept_mappings=concept_mappings,
                candidates=ranked,
                total_found=search_result.get("total_found", len(ranked)),
                primary_total_found=search_result.get("primary_total_found"),
                max_results=search_result.get("max_results"),
                source=search_result.get("source", repository_label),
                repository=search_result.get("repository", repository_label),
                search_term=search_result.get("search_term") or None,
                search_strategies=search_result.get("search_strategies", []),
                has_more=search_result.get("has_more", False),
                retrieved_count=len(ranked),
                retrievable_total=search_result.get("retrievable_total"),
                include_text_broad=search_options.include_text_broad,
                text_broad_total_found=search_result.get("text_broad_total_found"),
                load_more_cursor=(
                    DatasetSearchCursor.model_validate(search_result["load_more_cursor"])
                    if search_result.get("load_more_cursor")
                    else None
                ),
            )
            result_payload = pipeline.dataset_search_result_payload(result)
            final_response = self._format_dataset_search_response(result)

            self.tracer.log_step(
                "respond",
                {
                    "label": "Respond",
                    "description": "Render ranked dataset results, warnings, and structured dataset_search payload",
                    "candidate_count": len(ranked),
                    "response_preview": final_response[:240],
                },
            )
            self.tracer.end_trace("agent_run", {"final_response": final_response})
            return final_response, self.tracer.get_traces(), result_payload

        except Exception as e:
            self.tracer.log_error("agent_run", str(e))
            return f"Error: {str(e)}", self.tracer.get_traces(), None
    
    def _plan(self, query: str) -> Dict[str, Any]:
        """Create an initial plan based on the query"""
        from domain.query_interpretation import is_dataset_discovery_query

        # Simple planning logic - in a real implementation, this would use an LLM
        plan = {
            "goal": query,
            "steps": [],
            "tools_needed": [],
            "estimated_iterations": 3
        }
        
        # Determine which tools might be needed based on query keywords
        query_lower = query.lower()
        is_dataset_query = is_dataset_discovery_query(query)
        
        # PubMed: literature search
        # Also trigger for disease queries, but not dataset-discovery phrasing
        has_literature_keywords = any(keyword in query_lower for keyword in ["search", "find", "article", "paper", "research", "pubmed", "literature", "study", "studies", "publication"])
        is_disease_query = any(keyword in query_lower for keyword in ["disease", "syndrome", "disorder", "condition"])
        
        if not is_dataset_query and (has_literature_keywords or is_disease_query):
            plan["tools_needed"].extend(["pubmed", "openalex", "europepmc"])

        # Expression Atlas: gene expression experiments and omics dataset queries
        # Dataset-discovery queries use the repository pipeline instead of this tool path.
        has_expression_keywords = (
            not is_dataset_query
            and any(
            keyword in query_lower
            for keyword in [
                "expression atlas",
                "gene expression",
                "expression",
                "transcriptome",
                "transcriptomic",
                "rna-seq",
                "rna seq",
                "rnaseq",
                "microarray",
                "omics",
                "dataset",
                "datasets",
                "data set",
            ]
        ))
        if has_expression_keywords:
            plan["tools_needed"].append("expression_atlas")
        
        # Gene/Protein information
        # Trigger on keywords OR if potential gene symbols are detected
        has_gene_keywords = any(keyword in query_lower for keyword in ["gene", "protein", "sequence"])
        potential_genes = self._extract_potential_gene_symbols(query)
        
        if has_gene_keywords or potential_genes:
            plan["tools_needed"].extend(["mygene", "uniprot"])
        
        # AlphaFold: protein structure
        if any(keyword in query_lower for keyword in ["structure", "alphafold", "fold", "3d"]):
            plan["tools_needed"].append("alphafold")
        
        # ClinVar: genetic variants and clinical significance
        # Also trigger for disease/syndrome queries
        is_disease_query = any(keyword in query_lower for keyword in ["disease", "syndrome", "disorder", "condition"])
        is_variant_query = any(keyword in query_lower for keyword in ["variant", "variants", "mutation", "mutations", "clinvar", "pathogenic", "clinical"])
        
        if is_variant_query or (is_disease_query and potential_genes):
            plan["tools_needed"].append("clinvar")
        
        # Summarization
        if any(keyword in query_lower for keyword in ["summarize", "summary"]):
            plan["tools_needed"].append("summarize")
            
        return plan

    def _filter_planned_tools(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Drop capabilities that are not registered (excluded via SCIAGENT_EXCLUDED_SOURCES or SCIAGENT_EXCLUDED_TOOLS)."""
        filtered = plan.copy()
        filtered["tools_needed"] = [
            tool_name
            for tool_name in plan.get("tools_needed", [])
            if self.registry.get_tool(tool_name)
        ]
        return filtered
    
    def _act(self, plan: Dict[str, Any], iteration: int) -> List[Dict[str, Any]]:
        """Execute planned actions using available tools"""
        results = []
        
        # Extract parameters from the original query for tool execution
        query = plan.get("goal", "")
        
        # Simple action execution - call real tools with extracted parameters
        for tool_name in plan.get("tools_needed", []):
            if iteration == 0:  # Only run tools on first iteration
                try:
                    tool = self.registry.get_tool(tool_name)
                    if tool:
                        # Extract parameters based on tool and query
                        params = self._extract_tool_parameters(tool_name, query)
                        if params:
                            # Handle special case for ClinVar condition search
                            if tool_name == "clinvar" and params.get("_use_condition_search"):
                                from tools.clinvar import search_clinvar_by_condition
                                params.pop("_use_condition_search")
                                result_data = search_clinvar_by_condition(**params)
                            else:
                                # Execute the actual tool
                                result_data = self.registry.execute_tool(tool_name, **params)
                            result = {
                                "tool": tool_name, 
                                "status": "success", 
                                "data": result_data,
                                "parameters": params
                            }
                        else:
                            result = {
                                "tool": tool_name, 
                                "status": "error", 
                                "error": f"Could not extract parameters for {tool_name} from query"
                            }
                        results.append(result)
                        self.tracer.log_step("tool_execution", result)
                except Exception as e:
                    error_result = {"tool": tool_name, "status": "error", "error": str(e)}
                    results.append(error_result)
                    self.tracer.log_step("tool_execution", error_result)
        
        return results
    
    def _extract_tool_parameters(self, tool_name: str, query: str) -> Dict[str, Any]:
        """Extract parameters for tool execution from the query"""
        query_lower = query.lower()
        
        if tool_name == "pubmed":
            # For PubMed, use the entire query as search term
            return {"query": query}

        elif tool_name in ("openalex", "europepmc"):
            return {"query": query}

        elif tool_name == "expression_atlas":
            return self._build_expression_atlas_params(query)
        
        elif tool_name == "mygene":
            # Look for gene symbols in the query
            gene_symbols = self._extract_gene_symbols(query)
            if gene_symbols:
                return {"symbol": gene_symbols[0]}  # Use first gene found
            return None
        
        elif tool_name == "uniprot":
            # Look for protein identifiers or gene symbols
            protein_ids = self._extract_protein_identifiers(query)
            if protein_ids:
                return {"identifier": protein_ids[0]}
            return None
        
        elif tool_name == "alphafold":
            # Look for UniProt IDs or gene symbols
            protein_ids = self._extract_protein_identifiers(query)
            if protein_ids:
                return {"uniprot_id": protein_ids[0]}
            return None
        
        elif tool_name == "clinvar":
            # Check if it's a disease query or gene query
            query_lower = query.lower()
            is_disease_query = any(keyword in query_lower for keyword in ["disease", "syndrome", "disorder", "condition"])
            
            if is_disease_query and not any(keyword in query_lower for keyword in ["variant", "mutation"]):
                # Search by disease/condition name
                # Extract disease name from query
                disease_name = self._extract_disease_name(query)
                if disease_name:
                    # Use the search_clinvar_by_condition function
                    return {"condition": disease_name, "_use_condition_search": True}
            
            # Otherwise, look for gene symbols for variant lookup
            gene_symbols = self._extract_gene_symbols(query)
            if not gene_symbols:
                cleaned_genes = [g for g in self._extract_potential_gene_symbols(query) 
                                if g not in ['MARFAN', 'ALZHEIMER', 'PARKINSON', 'CANCER', 'CYSTIC']]
                gene_symbols = cleaned_genes
            
            if gene_symbols:
                return {"gene_symbol": gene_symbols[0]}
            
            # For disease queries without specific genes, use the disease name
            if is_disease_query:
                disease_name = self._extract_disease_name(query)
                if disease_name:
                    return {"condition": disease_name, "_use_condition_search": True}
            
            return None
        
        elif tool_name == "summarize":
            # Summarize text from previous results
            text_to_summarize = self._extract_text_for_summarization(plan)
            if text_to_summarize:
                return {"text": text_to_summarize}
            return None
        
        return None
    
    def _extract_disease_name(self, query: str) -> str:
        """Extract disease/syndrome name from query"""
        query_lower = query.lower()
        
        # Common patterns to remove
        patterns_to_remove = [
            'tell me about', 'what is', 'genes involved in', 'genes associated with',
            'what causes', 'information on', 'information about', 'genetics of',
            'genetic basis of', 'find', 'search', 'get', 'show'
        ]
        
        cleaned_query = query_lower
        for pattern in patterns_to_remove:
            cleaned_query = cleaned_query.replace(pattern, '')
        
        # Clean up extra spaces and common words
        cleaned_query = ' '.join(cleaned_query.split())
        
        # Remove trailing question marks, etc
        cleaned_query = cleaned_query.strip('?.,;:')

        # Drop trailing query/action words so "marfan syndrome variants" → "marfan syndrome"
        trailing_words = {
            'variant', 'variants', 'mutation', 'mutations', 'gene', 'genes',
            'linked', 'associated', 'involved', 'related', 'clinical', 'pathogenic',
            'clinvar', 'literature', 'articles', 'paper', 'papers', 'research',
            'what', 'which', 'are', 'is', 'the', 'to', 'with', 'for', 'in', 'on', 'a', 'an',
        }
        words = cleaned_query.split()
        while words and words[-1] in trailing_words:
            words.pop()
        cleaned_query = ' '.join(words).strip()

        return cleaned_query
    
    def _extract_text_for_summarization(self, plan: Dict[str, Any]) -> str:
        """Extract text from previous results for summarization"""
        # Get results from previous iterations
        iteration_results = plan.get("iteration_results", [])
        
        texts = []
        for result in iteration_results:
            if result.get("status") == "success":
                data = result.get("data", {})
                
                # Extract text from different tool types
                if isinstance(data, dict):
                    # Gene/Protein summaries
                    if data.get("summary"):
                        texts.append(data["summary"])
                    
                    # PubMed abstracts
                    if data.get("results"):
                        for article in data["results"][:3]:  # First 3 articles
                            if article.get("abstract"):
                                texts.append(article["abstract"])
        
        return "\n\n".join(texts) if texts else ""
    
    def _extract_potential_gene_symbols(self, query: str) -> List[str]:
        """Extract potential gene symbols from query using pattern matching"""
        import re
        
        # Gene symbols are typically 2-10 characters, alphanumeric, often all caps
        # Common patterns: BRCA1, TP53, APOE, SIGMAR1, CD4, IL6, etc.
        words = query.split()
        potential_genes = []
        
        for word in words:
            # Remove punctuation
            clean_word = re.sub(r'[^\w]', '', word)
            
            # Check if it looks like a gene symbol:
            # - 2-10 characters
            # - Contains at least one letter
            # - Mostly uppercase or can be converted
            if 2 <= len(clean_word) <= 10:
                upper_word = clean_word.upper()
                # Must have at least one letter and not be a common word
                # Gene symbols typically: start with a letter, contain numbers or multiple caps
                common_words = ['TELL', 'ABOUT', 'WHAT', 'THE', 'GET', 'SHOW', 'FIND', 'ME', 'IS', 'ARE', 
                               'AND', 'OR', 'FOR', 'WITH', 'FROM', 'TO', 'OF', 'IN', 'ON', 'AT', 'BY',
                               'FUNCTION', 'STRUCTURE', 'PROTEIN', 'GENE', 'GENES', 'THAT', 'THIS', 'DOES', 'DO',
                               'HOW', 'WHY', 'WHEN', 'WHERE', 'CAN', 'HAS', 'HAVE', 'HAD', 'WAS', 'WERE',
                               'SYNDROME', 'DISEASE', 'DISORDER', 'CONDITION', 'INVOLVED', 'ASSOCIATED',
                               'CAUSES', 'CAUSE', 'MARFAN', 'ALZHEIMER', 'PARKINSON', 'CANCER', 'CYSTIC',
                               'FIBROSIS', 'HUNTINGTON', 'MUSCULAR', 'DYSTROPHY', 'SICKLE', 'CELL',
                               'VARIANT', 'VARIANTS', 'MUTATION', 'MUTATIONS', 'PATHOGENIC', 'CLINVAR',
                               'LINKED', 'LITERATURE', 'ARTICLES', 'SEARCH', 'RESEARCH']
                # Gene symbol heuristic: has a number OR is 3+ chars (excluding very common words)
                if (re.match(r'^[A-Z][A-Z0-9]+$', upper_word) and 
                    upper_word not in common_words and
                    (re.search(r'\d', upper_word) or len(upper_word) >= 3)):
                    potential_genes.append(upper_word)
        
        return potential_genes
    
    def _extract_gene_symbols(self, query: str) -> List[str]:
        """Extract potential gene symbols from query (legacy - uses hardcoded list)"""
        # Common gene symbols mentioned in queries
        common_genes = [
            "BRCA1", "BRCA2", "TP53", "APOE", "CFTR", "TNF", "IL6", "VEGFA",
            "EGFR", "MYC", "RB1", "PTEN", "KRAS", "PIK3CA", "AKT1", "SIGMAR1"
        ]
        
        found_genes = []
        query_upper = query.upper()
        
        for gene in common_genes:
            if gene in query_upper:
                found_genes.append(gene)
        
        return found_genes
    
    def _extract_protein_identifiers(self, query: str) -> List[str]:
        """Extract potential protein identifiers from query"""
        # Look for UniProt accession patterns (like P38398)
        import re
        uniprot_pattern = r'\b[A-NR-Z][0-9][A-Z][A-Z0-9][A-Z0-9][0-9]\b'
        matches = re.findall(uniprot_pattern, query)
        
        if matches:
            return matches
        
        # Fall back to gene symbols
        return self._extract_gene_symbols(query)
    
    def _observe(self, action_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze the results of executed actions"""
        observations = {
            "total_actions": len(action_results),
            "successful_actions": len([r for r in action_results if r.get("status") == "success"]),
            "failed_actions": len([r for r in action_results if r.get("status") == "error"]),
            "results": action_results
        }
        
        self.tracer.log_step("observe", observations)
        return observations
    
    def _synthesize(self, plan: Dict[str, Any], observations: Dict[str, Any], original_query: str) -> Dict[str, Any]:
        """Update the plan based on observations"""
        updated_plan = plan.copy()
        
        # Simple synthesis logic
        if observations["failed_actions"] > 0:
            updated_plan["needs_retry"] = True
        else:
            updated_plan["needs_retry"] = False
            
        updated_plan["iteration_results"] = observations["results"]
        
        self.tracer.log_step("synthesize", {"updated_plan": updated_plan})
        return updated_plan
    
    def _is_complete(self, plan: Dict[str, Any], observations: Dict[str, Any]) -> bool:
        """Determine if the agent has enough information to provide a complete answer"""
        # Simple completion logic
        return (
            observations["successful_actions"] > 0 and 
            not plan.get("needs_retry", False)
        )
    
    def _normalize_results(self, results: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Map tool-result text terms to formal ontology terms."""
        try:
            from tools.ontology_normalizer import normalize_tool_results
            return normalize_tool_results(results)
        except Exception as e:
            return results, {
                "status": "error",
                "error": str(e),
                "total_terms": 0,
                "matched": 0,
                "unmatched": 0,
                "mappings": [],
            }

    def _final_synthesis(self, results: List[Dict[str, Any]], query: str) -> str:
        """Generate the final response based on all collected results"""
        if not results:
            return "I wasn't able to gather any information for your query. Please try rephrasing your question."
        
        successful_results = [r for r in results if r.get("status") == "success"]
        
        if not successful_results:
            return "I encountered errors while trying to gather information for your query."
        
        # Format response based on the tools used and data received
        response = f"Based on your query '{query}', I found the following information:\n\n"
        
        for i, result in enumerate(successful_results, 1):
            tool_name = result.get("tool", "Unknown")
            data = result.get("data", "No data available")
            params = result.get("parameters", {})
            
            # Format different types of results
            if tool_name == "pubmed":
                response += self._format_literature_results(i, data, "PubMed Search Results")
            elif tool_name == "openalex":
                response += self._format_literature_results(i, data, "OpenAlex Search Results")
            elif tool_name == "europepmc":
                response += self._format_literature_results(i, data, "Europe PMC Search Results")
            elif tool_name == "expression_atlas":
                response += self._format_expression_atlas_results(i, data)
            
            elif tool_name == "mygene":
                if isinstance(data, dict) and data.get("found"):
                    response += f"{i}. **Gene Information ({data.get('symbol', 'Unknown')})**:\n"
                    response += f"   Name: {data.get('name', 'Unknown')}\n"
                    response += f"   Entrez ID: {data.get('entrez_id', 'N/A')}\n"
                    response += f"   Type: {data.get('type', 'Unknown')}\n"
                    if data.get("summary"):
                        summary = data["summary"][:300] + "..." if len(data["summary"]) > 300 else data["summary"]
                        response += f"   Summary: {summary}\n"
                    response += f"   Source: {data.get('source', 'Unknown')}\n\n"
                else:
                    response += f"{i}. **Gene Information**: {data.get('error', 'No information found')}\n\n"
            
            elif tool_name == "uniprot":
                if isinstance(data, dict) and data.get("found"):
                    response += f"{i}. **Protein Information ({data.get('accession', 'Unknown')})**:\n"
                    response += f"   Name: {data.get('protein_name', 'Unknown')}\n"
                    response += f"   Organism: {data.get('organism', {}).get('scientific_name', 'Unknown')}\n"
                    response += f"   Length: {data.get('length', 'Unknown')} amino acids\n"
                    if data.get("summary"):
                        summary = data["summary"][:300] + "..." if len(data["summary"]) > 300 else data["summary"]
                        response += f"   Summary: {summary}\n"
                    response += f"   Source: {data.get('source', 'Unknown')}\n\n"
                else:
                    response += f"{i}. **Protein Information**: {data.get('error', 'No information found')}\n\n"
            
            elif tool_name == "alphafold":
                if isinstance(data, dict) and data.get("found"):
                    response += f"{i}. **AlphaFold Structure for {data.get('gene', 'Unknown')} ({data.get('uniprot_id', 'Unknown')})**:\n"
                    response += f"   Protein: {data.get('protein_name', 'Unknown')}\n"
                    response += f"   Organism: {data.get('organism', 'Unknown')}\n"
                    response += f"   Sequence Length: {data.get('sequence_length', 'Unknown')} residues\n"
                    response += f"   Overall Confidence: {data.get('confidence_score', 'Unknown')}/100\n"
                    confidence_info = data.get("confidence_metrics", {})
                    if confidence_info:
                        response += f"   Quality: {confidence_info.get('category', 'Unknown')} ({confidence_info.get('description', 'N/A')})\n"
                        response += f"   Confidence Breakdown:\n"
                        response += f"     - Very High: {confidence_info.get('fraction_very_high', 0)*100:.1f}%\n"
                        response += f"     - Confident: {confidence_info.get('fraction_confident', 0)*100:.1f}%\n"
                        response += f"     - Low: {confidence_info.get('fraction_low', 0)*100:.1f}%\n"
                        response += f"     - Very Low: {confidence_info.get('fraction_very_low', 0)*100:.1f}%\n"
                    response += f"   AlphaFold ID: {data.get('alphafold_id', 'Unknown')}\n"
                    response += f"   Model Version: {data.get('latest_version', 'Unknown')}\n"
                    response += f"   PDB File: {data.get('pdb_url', 'N/A')}\n"
                    response += f"   View Structure: {data.get('structure_url', 'N/A')}\n"
                    response += f"   Source: {data.get('source', 'Unknown')}\n\n"
                else:
                    response += f"{i}. **AlphaFold Structure**: {data.get('error', 'No structure found')}\n\n"
            
            elif tool_name == "clinvar":
                if isinstance(data, dict) and data.get("variants"):
                    variants = data["variants"]
                    total = data.get("total_variants", len(variants))
                    showing = data.get("showing", len(variants))
                    gene = data.get("gene", "Unknown")
                    
                    response += f"{i}. **ClinVar Variants for {gene}** (showing {showing} of {total} total):\n"
                    
                    for j, variant in enumerate(variants[:5], 1):  # Show first 5
                        title = variant.get("title", "Unknown variant")
                        sig = variant.get("clinical_significance", "Unknown")
                        review = variant.get("review_status", "Unknown")
                        var_type = variant.get("variation_type", "Unknown")
                        
                        response += f"   {j}. {title}\n"
                        response += f"      Clinical Significance: {sig}\n"
                        response += f"      Review Status: {review}\n"
                        response += f"      Variant Type: {var_type}\n"
                        if variant.get("url"):
                            response += f"      URL: {variant['url']}\n"
                        response += "\n"
                    
                    if total > 5:
                        response += f"   ... and {total - 5} more variants\n"
                    response += f"   Source: {data.get('source', 'ClinVar')}\n\n"
                elif isinstance(data, dict) and data.get("error"):
                    response += f"{i}. **ClinVar Variants**: {data['error']}\n\n"
                else:
                    response += f"{i}. **ClinVar Variants**: No variants found\n\n"
            
            elif tool_name == "summarize":
                if isinstance(data, dict) and data.get("summary"):
                    response += f"{i}. **Summary**:\n"
                    response += f"{data['summary']}\n"
                    if data.get("model"):
                        response += f"   Generated by: {data.get('provider')} ({data.get('model')})\n"
                    response += "\n"
                elif isinstance(data, dict) and data.get("error"):
                    response += f"{i}. **Summary**: {data['error']}\n\n"
                else:
                    response += f"{i}. **Summary**: No summary available\n\n"
            
            else:
                # Generic formatting for other tools
                response += f"{i}. **{tool_name}**: {data}\n\n"
        
        return response

    def _format_literature_results(self, index: int, data: Any, label: str) -> str:
        """Format literature search results from PubMed, OpenAlex, or Europe PMC."""
        if isinstance(data, dict) and "results" in data:
            articles = data["results"]
            if articles:
                block = f"{index}. **{label}** (found {len(articles)} articles):\n"
                for j, article in enumerate(articles[:3], 1):
                    title = article.get("title", "No title")
                    authors = ", ".join(article.get("authors", [])[:3])
                    year = article.get("year", "Unknown year")
                    block += f"   {j}. {title}\n"
                    block += f"      Authors: {authors} ({year})\n"
                    if article.get("abstract"):
                        abstract = article["abstract"]
                        if len(abstract) > 200:
                            abstract = abstract[:200] + "..."
                        block += f"      Abstract: {abstract}\n"
                    block += f"      URL: {article.get('url', 'N/A')}\n\n"
                return block
            return f"{index}. **{label}**: No articles found for the query.\n\n"
        if isinstance(data, dict) and data.get("error"):
            return f"{index}. **{label}**: {data['error']}\n\n"
        return f"{index}. **{label}**: {data}\n\n"

    def _format_expression_atlas_results(self, index: int, data: Any) -> str:
        """Format Expression Atlas experiment search results."""
        if isinstance(data, dict) and "results" in data:
            experiments = data["results"]
            if experiments:
                total = data.get("total_found", len(experiments))
                primary = data.get("primary_total_found", total)
                block = (
                    f"{index}. **Expression Atlas Search Results** "
                    f"(showing {len(experiments)} of {total} experiments"
                )
                if primary != total:
                    block += f"; primary strategy: {primary}"
                block += "):\n"
                strategies = data.get("search_strategies") or []
                if strategies:
                    block += "   Search strategies:\n"
                    for summary in strategies:
                        block += (
                            f"     - {summary.get('strategy')}: "
                            f"{summary.get('total_found', 0)} hits "
                            f"({summary.get('search_term', '')})\n"
                        )
                for j, experiment in enumerate(experiments[:5], 1):
                    title = experiment.get("title", "No title")
                    accession = experiment.get("accession", "Unknown")
                    species = experiment.get("species") or "Unknown species"
                    experiment_type = experiment.get("experiment_type") or "Unknown type"
                    strategy = experiment.get("retrieval_strategy")
                    block += f"   {j}. {title}\n"
                    block += f"      Accession: {accession}\n"
                    block += f"      Species: {species}\n"
                    block += f"      Type: {experiment_type}\n"
                    if strategy:
                        block += f"      Strategy: {strategy}\n"
                    block += f"      URL: {experiment.get('url', 'N/A')}\n\n"
                if total > 5:
                    block += f"   ... and {total - 5} more experiments\n"
                block += f"   Source: {data.get('source', 'Expression Atlas')}\n\n"
                return block
            return f"{index}. **Expression Atlas Search Results**: No experiments found for the query.\n\n"
        if isinstance(data, dict) and data.get("error"):
            return f"{index}. **Expression Atlas Search Results**: {data['error']}\n\n"
        return f"{index}. **Expression Atlas Search Results**: {data}\n\n"

    def _build_expression_atlas_params(self, query: str) -> Dict[str, Any]:
        """Build a focused Expression Atlas query instead of sending raw chat text."""
        from domain.query_interpretation import interpret_dataset_query, is_dataset_discovery_query

        params: Dict[str, Any] = {}
        species = self._extract_species_filter(query)

        if is_dataset_discovery_query(query):
            interpreted = interpret_dataset_query(query)
            params["interpreted_query"] = interpreted.model_dump()
            params["query"] = query
            if not species and interpreted.organism == "human":
                species = "Homo sapiens"
        else:
            params["query"] = query

        if species:
            params["species"] = species
        return params

    def _extract_species_filter(self, query: str) -> str | None:
        """Extract an optional species filter from the query text."""
        query_lower = query.lower()
        if "homo sapiens" in query_lower:
            return "Homo sapiens"
        if re.search(r"\bhuman(s)?\b", query_lower):
            return "Homo sapiens"
        if "mus musculus" in query_lower:
            return "Mus musculus"
        if re.search(r"\bmouse\b", query_lower):
            return "Mus musculus"
        if "rattus norvegicus" in query_lower:
            return "Rattus norvegicus"
        if re.search(r"\brat(s)?\b", query_lower):
            return "Rattus norvegicus"
        return None

    def _format_dataset_search_response(self, result) -> str:
        """Brief chat summary; full details live in the structured dataset_search payload."""
        repository = result.repository or "repository"
        if not result.candidates:
            if result.total_found:
                return (
                    f"{repository} search found {result.total_found} potential matches, "
                    "but record retrieval failed or returned no usable metadata. "
                    "See details below."
                )
            return (
                f"No matching datasets were found in {repository} "
                f"({result.total_found} raw hits). See details below."
            )

        count = len(result.candidates)
        dataset_word = "dataset" if count == 1 else "datasets"
        total = result.total_found or count
        if total > count:
            limit_note = ""
            if result.max_results:
                if " + " in repository:
                    env_hint = "GEO_MAX_RESULTS / EXPRESSION_ATLAS_MAX_RESULTS"
                else:
                    env_hint = (
                        "GEO_MAX_RESULTS"
                        if repository == "GEO"
                        else "EXPRESSION_ATLAS_MAX_RESULTS"
                    )
                limit_note = f" ({env_hint}={result.max_results})"
            return (
                f"Showing {count} of {total:,} {repository} hits{limit_note} — "
                f"{count} ranked {dataset_word} by evidence. "
                "See ranked results below for match status and export context."
            )
        return (
            f"Found {count} ranked {dataset_word} from {result.source}. "
            "See ranked results below for evidence, match status, and export context."
        )
