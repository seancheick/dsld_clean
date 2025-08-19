#!/usr/bin/env python3
"""
Configuration file for Amazon Best-Sellers Multi-Category Scraper.

Add your Amazon bestseller URLs and desired output filenames here.
Each configuration should have:
- url: The Amazon bestseller category URL
- output_file: The desired JSON filename (will be saved in scripts/scrapers/)
- description: A human-readable description of the category

Example Amazon bestseller URLs:
- Vitamins & Supplements: /zgbs/hpc/23675621011
- Sports Nutrition: /zgbs/hpc/6973678011
- Health & Personal Care: /zgbs/hpc/3760901
- Beauty & Personal Care: /zgbs/beauty/11055981
- Baby & Child Care: /zgbs/baby-products/166777011
"""

# Configure your scraping targets here
SCRAPE_CONFIGS = [
    {
        "url": "https://www.amazon.com/Best-Sellers-Health-Household-Amino-Acid-Nutritional-Supplements/zgbs/hpc/10781161/ref=zg_bs_nav_hpc_2_23675621011",
        "output_file": "amazon_bestseller_amino_acids.json",
        "description": "Amino Acids"
    },
    {
        "url": "https://www.amazon.com/Best-Sellers-Health-Household-5-HTP-Nutritional-Supplements/zgbs/hpc/3773791/ref=zg_bs_nav_hpc_3_10781161",
        "output_file": "amazon_bestseller_5HTP.json",
        "description": "5-HTP"
    },
    {
        "url": "https://www.amazon.com/Best-Sellers-Health-Household-Acetyl-L-Carnitine-Nutritional-Supplements/zgbs/hpc/3773111/ref=zg_bs_nav_hpc_3_3773791",
        "output_file": "amazon_bestseller_Acetyl_L_Carnitine.json",
        "description": "Acetyl L-Carnitine"
    },
    {
        "url": "https://www.amazon.com/Best-Sellers-Health-Household-Branched-Chain-Amino-Acids-Nutritional-Supplements/zgbs/hpc/6939949011/ref=zg_bs_nav_hpc_3_3773111",
        "output_file": "amazon_bestseller_bcaas.json",
        "description": "BCAAs"
    },
    {
        "url": "https://www.amazon.com/Best-Sellers-Health-Household-Carnitine-Nutritional-Supplements/zgbs/hpc/6939947011/ref=zg_bs_nav_hpc_3_6939949011",
        "output_file": "amazon_bestseller_carnitine.json",
        "description": "Carnitine"
    },
    {
        "url": "https://www.amazon.com/Best-Sellers-Health-Household-Creatine-Nutritional-Supplements/zgbs/hpc/3773431/ref=zg_bs_nav_hpc_3_6939947011",
        "output_file": "amazon_bestseller_creatine.json",
        "description": "Creatine"
    },
      {
        "url": "https://www.amazon.com/Best-Sellers-Health-Household-L-Arginine-Nutritional-Supplements/zgbs/hpc/6939950011/ref=zg_bs_nav_hpc_3_3773431",
        "output_file": "amazon_bestseller_l_arginine.json",
        "description": "l-arginine"
    },
       {
        "url": "https://www.amazon.com/Best-Sellers-Health-Household-L-Glutamine-Nutritional-Supplements/zgbs/hpc/6939952011/ref=zg_bs_nav_hpc_3_6939950011",
        "output_file": "amazon_bestseller_l_glutamine.json",
        "description": "l-glutamine"
    },
       {
        "url": "https://www.amazon.com/Best-Sellers-Health-Household-L-Lysine-Nutritional-Supplements/zgbs/hpc/6940111011/ref=zg_bs_nav_hpc_3_6939952011",
        "output_file": "amazon_bestseller_l_lysine.json",
        "description": "l-lysine"
    },
    # Add more configurations here following this format:
    # {
    #     "url": "https://www.amazon.com/Best-Sellers-Health-Personal-Care/zgbs/hpc/3760901",
    #     "output_file": "amazon_bestseller_health_personal_care.json",
    #     "description": "Health & Personal Care"
    # },
    # {
    #     "url": "https://www.amazon.com/Best-Sellers-Beauty-Personal-Care/zgbs/beauty/11055981",
    #     "output_file": "amazon_bestseller_beauty.json",
    #     "description": "Beauty & Personal Care"
    # },
]

# You can also define configurations programmatically if needed
def get_custom_configs():
    """
    Return additional configurations programmatically.
    Useful if you want to generate configs based on some logic.
    """
    return []

# Combine all configurations
def get_all_configs():
    """
    Returns all scraping configurations.
    """
    return SCRAPE_CONFIGS + get_custom_configs()
