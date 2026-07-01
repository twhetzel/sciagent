"""
AlphaFold tool - get protein structure information from AlphaFold database
"""

import requests
import os
import re
from typing import Dict, Any, List, Optional


def get_alphafold(uniprot_id: str) -> Dict[str, Any]:
    """
    Get protein structure information from AlphaFold database
    
    Args:
        uniprot_id: UniProt accession ID or gene symbol
        
    Returns:
        Dictionary containing AlphaFold structure information
    """
    try:
        # If it's a gene symbol, first convert to UniProt ID
        actual_uniprot_id = uniprot_id
        if not _is_uniprot_accession(uniprot_id):
            # Try to convert gene symbol to UniProt ID using the main get_uniprot function
            from .uniprot import get_uniprot
            protein_result = get_uniprot(uniprot_id)
            if protein_result.get("found"):
                actual_uniprot_id = protein_result.get("accession")
                if not actual_uniprot_id:
                    return {
                        "uniprot_id": uniprot_id,
                        "error": f"No UniProt ID found for gene symbol '{uniprot_id}'",
                        "found": False
                    }
            else:
                return {
                    "uniprot_id": uniprot_id,
                    "error": f"Could not find protein information for '{uniprot_id}': {protein_result.get('error', 'Unknown error')}",
                    "found": False
                }
        
        base_url = "https://alphafold.ebi.ac.uk/api"
        
        # Get AlphaFold entry information
        entry_url = f"{base_url}/prediction/{actual_uniprot_id}"
        
        response = requests.get(entry_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return {
                "uniprot_id": actual_uniprot_id,
                "error": f"No AlphaFold structure found for UniProt ID '{actual_uniprot_id}'",
                "found": False
            }
        
        # Extract structure information
        structure_info = _extract_structure_info(data, actual_uniprot_id)
        
        # Get additional metadata if available
        metadata = _get_structure_metadata(uniprot_id)
        if metadata:
            structure_info.update(metadata)
        
        return structure_info
        
    except requests.exceptions.RequestException as e:
        return {"uniprot_id": uniprot_id, "error": f"Network error: {str(e)}", "found": False}
    except Exception as e:
        return {"uniprot_id": uniprot_id, "error": f"Error fetching AlphaFold data: {str(e)}", "found": False}


def _extract_structure_info(data: List[Dict[str, Any]], uniprot_id: str) -> Dict[str, Any]:
    """Extract structure information from AlphaFold API response"""
    if not data:
        return {"uniprot_id": uniprot_id, "found": False}
    
    # Get the first (usually best) prediction
    prediction = data[0] if isinstance(data, list) else data
    
    return {
        "uniprot_id": uniprot_id,
        "alphafold_id": prediction.get("entryId", uniprot_id),
        "confidence_score": prediction.get("globalMetricValue"),  # Fixed: globalMetricValue not confidenceScore
        "confidence_metrics": _extract_confidence_metrics(prediction),
        "sequence_length": prediction.get("sequenceEnd", 0) - prediction.get("sequenceStart", 0) + 1,  # Fixed: calculate from start/end
        "organism": prediction.get("organismScientificName"),  # Fixed: organismScientificName
        "organism_tax_id": prediction.get("taxId"),  # Fixed: taxId not organismTaxId
        "gene": prediction.get("gene"),
        "protein_name": prediction.get("uniprotDescription"),
        "pdb_url": prediction.get("pdbUrl"),  # Use actual URL from API
        "structure_url": _get_structure_url(uniprot_id),
        "viewer_url": _get_viewer_url(uniprot_id),
        "model_date": prediction.get("modelCreatedDate"),
        "latest_version": prediction.get("latestVersion"),
        "found": True,
        "source": "AlphaFold"
    }


def _extract_confidence_metrics(prediction: Dict[str, Any]) -> Dict[str, Any]:
    """Extract confidence metrics from prediction data"""
    confidence = prediction.get("globalMetricValue", 0)
    
    # AlphaFold confidence categories
    if confidence >= 90:
        confidence_category = "Very high"
        confidence_description = "Very high confidence (>90%)"
    elif confidence >= 70:
        confidence_category = "Confident"
        confidence_description = "Confident (70-90%)"
    elif confidence >= 50:
        confidence_category = "Low confidence"
        confidence_description = "Low confidence (50-70%)"
    else:
        confidence_category = "Very low confidence"
        confidence_description = "Very low confidence (<50%)"
    
    return {
        "overall_confidence": confidence,
        "category": confidence_category,
        "description": confidence_description,
        "fraction_very_high": prediction.get("fractionPlddtVeryHigh", 0),
        "fraction_confident": prediction.get("fractionPlddtConfident", 0),
        "fraction_low": prediction.get("fractionPlddtLow", 0),
        "fraction_very_low": prediction.get("fractionPlddtVeryLow", 0)
    }


def _get_pdb_url(uniprot_id: str) -> str:
    """Get PDB download URL for the structure"""
    return f"https://alphafold.ebi.ac.uk/files/AF-{uniprot_id}-F1-model_v4.pdb"


def _get_structure_url(uniprot_id: str) -> str:
    """Get structure information URL"""
    return f"https://alphafold.ebi.ac.uk/entry/{uniprot_id}"


def _get_viewer_url(uniprot_id: str) -> str:
    """Get 3D structure viewer URL"""
    return f"https://alphafold.ebi.ac.uk/entry/{uniprot_id}"


def _get_structure_metadata(uniprot_id: str) -> Optional[Dict[str, Any]]:
    """Get additional structure metadata"""
    try:
        metadata_url = f"https://alphafold.ebi.ac.uk/api/metadata/{uniprot_id}"
        
        response = requests.get(metadata_url, timeout=30)
        if response.status_code == 200:
            metadata = response.json()
            return {
                "protein_name": metadata.get("proteinName"),
                "gene_names": metadata.get("geneNames"),
                "organism": metadata.get("organism"),
                "function": metadata.get("function"),
                "publication_date": metadata.get("publicationDate"),
                "last_updated": metadata.get("lastUpdated")
            }
    except Exception:
        pass  # Metadata is optional
    
    return None


def get_confidence_analysis(uniprot_id: str) -> Dict[str, Any]:
    """
    Get detailed confidence analysis for a protein structure
    
    Args:
        uniprot_id: UniProt accession ID
        
    Returns:
        Dictionary containing confidence analysis
    """
    try:
        # Get the main structure data
        structure_data = get_alphafold(uniprot_id)
        
        if "error" in structure_data:
            return structure_data
        
        # Get detailed confidence data
        confidence_url = f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot_id}"
        
        response = requests.get(confidence_url, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return {"uniprot_id": uniprot_id, "error": "No confidence data available"}
        
        prediction = data[0] if isinstance(data, list) else data
        confidence_metrics = prediction.get("confidenceScore", 0)
        per_residue_conf = prediction.get("perResidueConfidence", [])
        
        # Analyze confidence distribution
        if per_residue_conf:
            high_conf = len([c for c in per_residue_conf if c >= 70])
            medium_conf = len([c for c in per_residue_conf if 50 <= c < 70])
            low_conf = len([c for c in per_residue_conf if c < 50])
            
            total_residues = len(per_residue_conf)
            
            return {
                "uniprot_id": uniprot_id,
                "overall_confidence": confidence_metrics,
                "confidence_distribution": {
                    "high_confidence": high_conf,
                    "medium_confidence": medium_conf,
                    "low_confidence": low_conf,
                    "total_residues": total_residues
                },
                "confidence_percentages": {
                    "high_confidence_pct": (high_conf / total_residues * 100) if total_residues > 0 else 0,
                    "medium_confidence_pct": (medium_conf / total_residues * 100) if total_residues > 0 else 0,
                    "low_confidence_pct": (low_conf / total_residues * 100) if total_residues > 0 else 0
                },
                "recommendation": _get_confidence_recommendation(confidence_metrics, high_conf, total_residues)
            }
        else:
            return {
                "uniprot_id": uniprot_id,
                "overall_confidence": confidence_metrics,
                "error": "Per-residue confidence data not available"
            }
            
    except requests.exceptions.RequestException as e:
        return {"uniprot_id": uniprot_id, "error": f"Network error: {str(e)}"}
    except Exception as e:
        return {"uniprot_id": uniprot_id, "error": f"Error analyzing confidence: {str(e)}"}


def _get_confidence_recommendation(overall_conf: float, high_conf_residues: int, total_residues: int) -> str:
    """Get recommendation based on confidence analysis"""
    if overall_conf >= 90 and high_conf_residues / total_residues >= 0.8:
        return "Structure is highly reliable for most applications"
    elif overall_conf >= 70 and high_conf_residues / total_residues >= 0.6:
        return "Structure is reliable for general analysis, but check low-confidence regions"
    elif overall_conf >= 50:
        return "Structure has moderate reliability; use with caution and verify critical regions"
    else:
        return "Structure has low reliability; consider alternative methods or experimental structures"


def search_alphafold_by_organism(organism: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search AlphaFold structures by organism
    
    Args:
        organism: Organism name or taxonomy ID
        limit: Maximum number of results
        
    Returns:
        List of matching structures
    """
    try:
        # Note: AlphaFold API doesn't have a direct organism search
        # This is a placeholder for future implementation
        return [{"error": "Organism search not yet implemented in AlphaFold API"}]
        
    except Exception as e:
        return [{"error": f"Error searching by organism: {str(e)}"}]


def get_structure_quality_metrics(uniprot_id: str) -> Dict[str, Any]:
    """
    Get structure quality metrics and validation information
    
    Args:
        uniprot_id: UniProt accession ID
        
    Returns:
        Dictionary containing quality metrics
    """
    try:
        structure_data = get_alphafold(uniprot_id)
        
        if "error" in structure_data:
            return structure_data
        
        # Get confidence analysis
        confidence_data = get_confidence_analysis(uniprot_id)
        
        return {
            "uniprot_id": uniprot_id,
            "structure_info": structure_data,
            "confidence_analysis": confidence_data,
            "quality_assessment": _assess_structure_quality(confidence_data),
            "usage_recommendations": _get_usage_recommendations(confidence_data)
        }
        
    except Exception as e:
        return {"uniprot_id": uniprot_id, "error": f"Error getting quality metrics: {str(e)}"}


def _assess_structure_quality(confidence_data: Dict[str, Any]) -> Dict[str, Any]:
    """Assess overall structure quality"""
    overall_conf = confidence_data.get("overall_confidence", 0)
    
    quality_score = "Unknown"
    if overall_conf >= 90:
        quality_score = "Excellent"
    elif overall_conf >= 70:
        quality_score = "Good"
    elif overall_conf >= 50:
        quality_score = "Fair"
    else:
        quality_score = "Poor"
    
    return {
        "quality_score": quality_score,
        "overall_confidence": overall_conf,
        "suitable_for": _get_suitable_applications(overall_conf)
    }


def _get_suitable_applications(confidence: float) -> List[str]:
    """Get list of suitable applications based on confidence score"""
    applications = []
    
    if confidence >= 70:
        applications.extend(["Homology modeling", "Drug design", "Functional analysis"])
    if confidence >= 50:
        applications.extend(["Comparative analysis", "Domain identification"])
    if confidence >= 30:
        applications.extend(["Low-resolution analysis", "General structure comparison"])
    
    return applications


def _get_usage_recommendations(confidence_data: Dict[str, Any]) -> List[str]:
    """Get usage recommendations based on confidence analysis"""
    recommendations = []
    overall_conf = confidence_data.get("overall_confidence", 0)
    
    if overall_conf >= 90:
        recommendations.append("Structure is highly reliable for most computational applications")
        recommendations.append("Suitable for detailed molecular dynamics simulations")
    elif overall_conf >= 70:
        recommendations.append("Structure is reliable for general analysis")
        recommendations.append("Check low-confidence regions before detailed analysis")
    elif overall_conf >= 50:
        recommendations.append("Use with caution and verify critical regions")
        recommendations.append("Consider experimental validation for important findings")
    else:
        recommendations.append("Structure has limited reliability")
        recommendations.append("Consider alternative prediction methods or experimental structures")
    
    return recommendations


def _is_uniprot_accession(identifier: str) -> bool:
    """Check if identifier is a UniProt accession number"""
    # UniProt accession pattern: 1-5 alphanumeric characters, underscore, 1-5 alphanumeric characters
    uniprot_pattern = r'^[A-NR-Z][0-9][A-Z][A-Z0-9][A-Z0-9][0-9]$'
    return bool(re.match(uniprot_pattern, identifier))
