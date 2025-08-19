#!/usr/bin/env python3
"""
Enhanced unmapped ingredient tracking - separate active vs inactive
"""

import json
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime

class UnmappedIngredientTracker:
    """Track unmapped ingredients with separation between active and inactive"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.unmapped_active = {
            "high_priority": [],
            "medium_priority": [], 
            "low_priority": [],
            "metadata": {
                "total_count": 0,
                "last_updated": "",
                "notes": "Active ingredients that affect quality/bioavailability scoring"
            }
        }
        
        self.unmapped_inactive = {
            "safety_review_needed": [],
            "general_excipients": [],
            "known_safe": [],
            "metadata": {
                "total_count": 0,
                "last_updated": "",
                "notes": "Inactive/other ingredients - check for safety issues"
            }
        }
    
    def categorize_active_ingredient(self, ingredient: str, frequency: int) -> str:
        """Categorize active ingredients by priority for mapping"""
        # High priority: frequently found, likely bioactive compounds
        high_priority_patterns = [
            'extract', 'standardized', 'proprietary', 'blend', 'complex',
            'coq10', 'ubiquinol', 'pqq', 'curcumin', 'resveratrol',
            'ashwagandha', 'rhodiola', 'bacopa', 'ginkgo', 'milk thistle',
            'saw palmetto', 'green tea', 'grape seed', 'pine bark',
            'lutein', 'zeaxanthin', 'lycopene', 'astaxanthin'
        ]
        
        # Medium priority: vitamins, minerals, amino acids
        medium_priority_patterns = [
            'vitamin', 'mineral', 'amino', 'acid', 'chelate', 'gluconate',
            'citrate', 'picolinate', 'bisglycinate', 'malate', 'succinate',
            'methylcobalamin', 'methylfolate', 'tocotrienol'
        ]
        
        ingredient_lower = ingredient.lower()
        
        # High frequency = high priority regardless of pattern
        if frequency >= 10:
            return "high_priority"
        
        # Pattern-based categorization
        if any(pattern in ingredient_lower for pattern in high_priority_patterns):
            return "high_priority" if frequency >= 5 else "medium_priority"
        
        if any(pattern in ingredient_lower for pattern in medium_priority_patterns):
            return "medium_priority" if frequency >= 3 else "low_priority"
        
        return "low_priority"
    
    def categorize_inactive_ingredient(self, ingredient: str, frequency: int) -> str:
        """Categorize inactive ingredients by safety priority"""
        # Safety review needed: unknown chemicals, preservatives, colors
        safety_review_patterns = [
            'preservative', 'color', 'dye', 'artificial', 'synthetic',
            'chemical', 'compound', 'solution', 'proprietary coating',
            'unknown', 'unidentified', 'ingredient x', 'additive'
        ]
        
        # Known safe: common excipients
        known_safe_patterns = [
            'cellulose', 'starch', 'flour', 'oil', 'wax', 'water',
            'gelatin', 'capsule', 'tablet', 'coating', 'glaze',
            'magnesium stearate', 'silicon dioxide', 'microcrystalline'
        ]
        
        ingredient_lower = ingredient.lower()
        
        if any(pattern in ingredient_lower for pattern in safety_review_patterns):
            return "safety_review_needed"
        
        if any(pattern in ingredient_lower for pattern in known_safe_patterns):
            return "known_safe"
        
        return "general_excipients"
    
    def process_unmapped_ingredients(self, unmapped_data: Dict[str, int], 
                                   active_ingredients: Set[str]) -> None:
        """Process unmapped ingredients and categorize them"""
        
        for ingredient, frequency in unmapped_data.items():
            ingredient_data = {
                "name": ingredient,
                "frequency": frequency,
                "first_seen": datetime.now().strftime("%Y-%m-%d"),
                "mapping_attempts": 0,
                "notes": ""
            }
            
            if ingredient in active_ingredients:
                # Categorize active ingredients
                priority = self.categorize_active_ingredient(ingredient, frequency)
                self.unmapped_active[priority].append(ingredient_data)
                self.unmapped_active["metadata"]["total_count"] += 1
            else:
                # Categorize inactive ingredients  
                category = self.categorize_inactive_ingredient(ingredient, frequency)
                self.unmapped_inactive[category].append(ingredient_data)
                self.unmapped_inactive["metadata"]["total_count"] += 1
    
    def save_tracking_files(self) -> None:
        """Save separate tracking files for active and inactive unmapped ingredients"""
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Sort all categories by frequency (highest first)
        for priority in ["high_priority", "medium_priority", "low_priority"]:
            self.unmapped_active[priority].sort(key=lambda x: x["frequency"], reverse=True)
        
        for category in ["safety_review_needed", "general_excipients", "known_safe"]:
            self.unmapped_inactive[category].sort(key=lambda x: x["frequency"], reverse=True)
        
        # Update metadata
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.unmapped_active["metadata"]["last_updated"] = timestamp
        self.unmapped_inactive["metadata"]["last_updated"] = timestamp
        
        # Save active unmapped ingredients
        active_file = self.output_dir / "unmapped_active_ingredients.json"
        with open(active_file, 'w') as f:
            json.dump(self.unmapped_active, f, indent=2)
        
        # Save inactive unmapped ingredients
        inactive_file = self.output_dir / "unmapped_inactive_ingredients.json" 
        with open(inactive_file, 'w') as f:
            json.dump(self.unmapped_inactive, f, indent=2)
        
        print(f"✅ Saved unmapped tracking files:")
        print(f"   Active: {active_file}")
        print(f"   Inactive: {inactive_file}")
        
        # Print summary
        print(f"\n📊 Unmapped Ingredient Summary:")
        print(f"   Active Ingredients:")
        print(f"     High Priority: {len(self.unmapped_active['high_priority'])}")
        print(f"     Medium Priority: {len(self.unmapped_active['medium_priority'])}")
        print(f"     Low Priority: {len(self.unmapped_active['low_priority'])}")
        print(f"   Inactive Ingredients:")
        print(f"     Safety Review Needed: {len(self.unmapped_inactive['safety_review_needed'])}")
        print(f"     General Excipients: {len(self.unmapped_inactive['general_excipients'])}")
        print(f"     Known Safe: {len(self.unmapped_inactive['known_safe'])}")

def create_sample_tracking_files():
    """Create sample unmapped ingredient tracking files"""
    output_dir = Path("/Users/seancheick/Downloads/dsld_clean")
    tracker = UnmappedIngredientTracker(output_dir)
    
    # Sample unmapped ingredients data (ingredient -> frequency)
    sample_unmapped = {
        "CoQ10 Ubiquinol": 15,
        "PQQ disodium salt": 8,
        "Ashwagandha KSM-66": 12,
        "Proprietary mushroom blend": 6,
        "Methylcobalamin": 20,
        "Vegetable coating": 25,
        "Unknown preservative X": 3,
        "Microcrystalline cellulose": 30,
        "Artificial flavor agent": 4,
        "Rice hull powder": 8,
        "Turmeric 95% curcumin": 10,
        "Magnesium stearate (vegetable)": 18
    }
    
    # Sample active ingredients set (would come from your ingredient processing)
    sample_active_ingredients = {
        "CoQ10 Ubiquinol", "PQQ disodium salt", "Ashwagandha KSM-66", 
        "Proprietary mushroom blend", "Methylcobalamin", "Turmeric 95% curcumin"
    }
    
    # Process and save
    tracker.process_unmapped_ingredients(sample_unmapped, sample_active_ingredients)
    tracker.save_tracking_files()

if __name__ == "__main__":
    create_sample_tracking_files()