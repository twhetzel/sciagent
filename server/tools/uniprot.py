"""
UniProt tool - get protein information from UniProt database
"""

import requests
import os
import re
from typing import Dict, Any, List, Optional


def get_uniprot(identifier: str) -> Dict[str, Any]:
    """
    Get protein information from UniProt
    
    Args:
        identifier: UniProt accession number or protein symbol
        
    Returns:
        Dictionary containing protein information
    """
    try:
        base_url = "https://rest.uniprot.org"
        
        # First, try to search for the identifier
        search_url = f"{base_url}/uniprotkb/search"
        
        # Format the query based on the identifier type
        if _is_uniprot_accession(identifier):
            # Direct accession search - use accession field
            query = f"accession:{identifier}"
        elif _is_gene_symbol(identifier):
            # Gene symbol search - use proper UniProt query format with human organism filter
            # Prioritize reviewed entries (Swiss-Prot) over unreviewed (TrEMBL)
            query = f"gene:{identifier} AND organism_id:9606 AND reviewed:true"
        else:
            # General search
            query = identifier
        
        search_params = {
            "query": query,
            "format": "json",
            "size": 1
        }
        
        response = requests.get(search_url, params=search_params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("results"):
            return {
                "identifier": identifier,
                "error": f"No protein found with identifier '{identifier}'",
                "found": False
            }
        
        protein_data = data["results"][0]
        
        # If we found a result, get detailed information
        accession = protein_data.get("primaryAccession")
        if accession:
            detail_url = f"{base_url}/uniprotkb/{accession}"
            detail_params = {
                "format": "json"
            }
            
            detail_response = requests.get(detail_url, params=detail_params, timeout=15)
            detail_response.raise_for_status()
            detailed_data = detail_response.json()
            
            return _format_protein_data(detailed_data)
        else:
            return _format_protein_data(protein_data)
            
    except requests.exceptions.RequestException as e:
        return {"identifier": identifier, "error": f"Network error: {str(e)}", "found": False}
    except Exception as e:
        return {"identifier": identifier, "error": f"Error fetching protein data: {str(e)}", "found": False}


def _format_protein_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Format protein data into a standardized structure"""
    return {
        "accession": data.get("primaryAccession", "Unknown"),
        "entry_name": data.get("uniProtkbId", "Unknown"),
        "protein_name": data.get("proteinDescription", {}).get("recommendedName", {}).get("fullName", {}).get("value", "Unknown"),
        "organism": _format_organism(data.get("organism", {})),
        "length": data.get("sequence", {}).get("length"),
        "sequence": data.get("sequence", {}).get("value"),
        "genes": _extract_genes(data.get("genes", [])),
        "comments": _extract_comments(data.get("comments", [])),
        "keywords": _extract_keywords(data.get("keywords", [])),
        "references": _extract_references(data.get("references", [])),
        "protein_existence": data.get("proteinExistence"),
        "ec_numbers": _extract_ec_numbers(data.get("ec", [])),
        "go_terms": _extract_uniprot_go_terms(data.get("go", [])),
        "pathways": _extract_uniprot_pathways(data.get("pathways", [])),
        "interactions": _extract_interactions(data.get("interaction", [])),
        "found": True,
        "source": "UniProt"
    }


def _format_organism(organism_data: Dict[str, Any]) -> Dict[str, Any]:
    """Format organism information"""
    if not organism_data:
        return {}
    
    taxonomy = organism_data.get("taxonomy", [])
    lineage = []
    if taxonomy:
        for taxon in taxonomy:
            if isinstance(taxon, dict):
                lineage.append(taxon.get("value", "Unknown"))
    
    return {
        "scientific_name": organism_data.get("scientificName", "Unknown"),
        "common_name": organism_data.get("commonName", "Unknown"),
        "taxonomy_id": organism_data.get("taxonId"),
        "lineage": lineage
    }


def _extract_genes(genes_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract gene information"""
    if not genes_data:
        return []
    
    genes = []
    for gene in genes_data:
        if isinstance(gene, dict):
            gene_info = {
                "name": gene.get("geneName", {}).get("value", "Unknown"),
                "type": gene.get("geneName", {}).get("type", "Unknown")
            }
            
            # Extract synonyms
            synonyms = gene.get("synonyms", [])
            if synonyms:
                gene_info["synonyms"] = [syn.get("value", "") for syn in synonyms if isinstance(syn, dict)]
            
            genes.append(gene_info)
    
    return genes


def _extract_comments(comments_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract comment information"""
    if not comments_data:
        return []
    
    comments = []
    for comment in comments_data:
        if isinstance(comment, dict):
            comment_info = {
                "type": comment.get("commentType", "Unknown"),
                "text": []
            }
            
            # Extract text from different comment types
            texts = comment.get("texts", [])
            for text in texts:
                if isinstance(text, dict):
                    comment_info["text"].append(text.get("value", ""))
            
            comments.append(comment_info)
    
    return comments


def _extract_keywords(keywords_data: List[Dict[str, Any]]) -> List[str]:
    """Extract keyword information"""
    if not keywords_data:
        return []
    
    keywords = []
    for keyword in keywords_data:
        if isinstance(keyword, dict):
            keywords.append(keyword.get("value", ""))
    
    return keywords


def _extract_references(references_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract reference information"""
    if not references_data:
        return []
    
    references = []
    for ref in references_data:
        if isinstance(ref, dict):
            ref_info = {
                "citation": ref.get("citation", {}).get("value", "Unknown"),
                "type": ref.get("citation", {}).get("type", "Unknown")
            }
            
            # Extract publication information
            publication = ref.get("publication", {})
            if publication:
                ref_info["publication"] = {
                    "title": publication.get("title", "Unknown"),
                    "authors": publication.get("authors", []),
                    "journal": publication.get("journal", "Unknown"),
                    "volume": publication.get("volume"),
                    "pages": publication.get("pages"),
                    "date": publication.get("date")
                }
            
            references.append(ref_info)
    
    return references


def _extract_ec_numbers(ec_data: List[Dict[str, Any]]) -> List[str]:
    """Extract EC numbers"""
    if not ec_data:
        return []
    
    ec_numbers = []
    for ec in ec_data:
        if isinstance(ec, dict):
            ec_numbers.append(ec.get("value", ""))
    
    return ec_numbers


def _extract_uniprot_go_terms(go_data: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Extract GO terms from UniProt"""
    if not go_data:
        return {}
    
    go_terms = {"biological_process": [], "molecular_function": [], "cellular_component": []}
    
    for go in go_data:
        if isinstance(go, dict):
            go_type = go.get("type", "").lower().replace(" ", "_")
            go_id = go.get("goId", "")
            go_name = go.get("name", "")
            
            if go_type in go_terms:
                go_terms[go_type].append(f"{go_id}: {go_name}")
    
    return go_terms


def _extract_uniprot_pathways(pathways_data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Extract pathway information from UniProt"""
    if not pathways_data:
        return []
    
    pathways = []
    for pathway in pathways_data:
        if isinstance(pathway, dict):
            pathways.append({
                "name": pathway.get("name", "Unknown pathway"),
                "id": pathway.get("database", {}).get("id", "Unknown ID"),
                "source": pathway.get("database", {}).get("name", "Unknown source")
            })
    
    return pathways


def _extract_interactions(interactions_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract protein interaction information"""
    if not interactions_data:
        return []
    
    interactions = []
    for interaction in interactions_data:
        if isinstance(interaction, dict):
            interaction_info = {
                "type": interaction.get("type", "Unknown"),
                "interactant": interaction.get("interactant", {}).get("name", "Unknown")
            }
            
            # Extract additional details
            details = interaction.get("details", [])
            if details:
                interaction_info["details"] = [detail.get("value", "") for detail in details if isinstance(detail, dict)]
            
            interactions.append(interaction_info)
    
    return interactions


def search_proteins_by_name(name: str, organism: str = "human", limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search for proteins by name
    
    Args:
        name: Protein name to search for
        organism: Organism to filter by (default: human)
        limit: Maximum number of results
        
    Returns:
        List of matching proteins
    """
    try:
        base_url = "https://rest.uniprot.org"
        search_url = f"{base_url}/uniprotkb/search"
        
        query = f"protein_name:{name}"
        if organism:
            # Convert organism name to taxonomy ID if needed
            if organism.lower() == "human":
                query += " AND organism_id:9606"
            elif organism.lower() == "mouse":
                query += " AND organism_id:10090"
            else:
                query += f" AND organism_id:{organism}"
        
        params = {
            "query": query,
            "format": "json",
            "size": limit
        }
        
        response = requests.get(search_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for hit in data.get("results", []):
            results.append({
                "accession": hit.get("primaryAccession", "Unknown"),
                "entry_name": hit.get("uniProtkbId", "Unknown"),
                "protein_name": hit.get("proteinDescription", {}).get("recommendedName", {}).get("fullName", {}).get("value", "Unknown"),
                "organism": hit.get("organism", {}).get("scientificName", "Unknown"),
                "length": hit.get("sequence", {}).get("length")
            })
        
        return results
        
    except requests.exceptions.RequestException as e:
        return [{"error": f"Network error: {str(e)}"}]
    except Exception as e:
        return [{"error": f"Error searching proteins: {str(e)}"}]


def _is_uniprot_accession(identifier: str) -> bool:
    """Check if identifier is a UniProt accession number"""
    # UniProt accession patterns:
    # - [OPQ][0-9][A-Z0-9]{3}[0-9] (6 characters, e.g., P12345)
    # - [A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2} (10 characters, e.g., A0A0B4J2F0)
    pattern1 = r'^[OPQ][0-9][A-Z0-9]{3}[0-9]$'  # 6-char format
    pattern2 = r'^[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$'  # 10-char format
    return bool(re.match(pattern1, identifier) or re.match(pattern2, identifier))


def _is_gene_symbol(identifier: str) -> bool:
    """Check if identifier is likely a gene symbol"""
    # Common gene symbols are 2-10 characters, alphanumeric, often all caps
    gene_pattern = r'^[A-Z0-9]{2,10}$'
    return bool(re.match(gene_pattern, identifier))
