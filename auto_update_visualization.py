#!/usr/bin/env python3
import argparse
import sys

# Visualization imports
import matplotlib.pyplot as plt
import numpy as np
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE

from embeddings_dedup import get_embeddings
from shared import g_c
from Logging import _setup_logging

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# Logging configuration
LOG_LEVEL = "INFO"  # Change to "DEBUG" for maximum verbosity
LOG_FILE = "auto_update.log"  # Single log file that gets appended to

# Set up custom logging for auto_update
logger = _setup_logging(LOG_FILE, LOG_LEVEL)

def create_embedding_visualization(mode=None, output_file="embedding_visualization.png"):
    """
    Create a visualization of the 200 previous selected titles using their embeddings.
    
    Args:
        mode (str): The mode name for cache key (optional, uses local cache.db)
        output_file (str): Output filename for the visualization
    """
    logger.info(f"Creating embedding visualization using local cache.db")
    
    # Get previous selections from the global cache (which uses local cache.db)
    previous_selections = g_c.get("previously_selected_selections_2")
    
    if not previous_selections:
        logger.warning("No previous selections found in local cache.db")
        return False
    
    logger.info(f"Found {len(previous_selections)} previous selections")
    
    # Limit to 200 most recent selections
    if len(previous_selections) > 200:
        previous_selections = previous_selections[-200:]
        logger.info(f"Limited to 200 most recent selections")
    
    # Extract titles and compute embeddings
    titles = [sel["title"] for sel in previous_selections]
    logger.info(f"Extracted {len(titles)} titles for embedding computation")
    
    # Set matplotlib to use a non-interactive backend to avoid font loading issues
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    logger.info("Set matplotlib backend to Agg")
    
    logger.info("Computing embeddings for titles...")
    
    # Extract titles and compute embeddings
    titles = [sel["title"] for sel in previous_selections]
    logger.info("Computing embeddings for titles...")
    
    embeddings = []
    valid_titles = []
    failed_titles = []
    
    logger.info(f"Starting embedding computation for {len(titles)} titles...")
    for i, title in enumerate(titles):
        if i % 10 == 0:  # Log progress every 10 titles
            logger.info(f"Processing title {i+1}/{len(titles)}")
        embedding = get_embeddings(title)
        if embedding is not None:
            embeddings.append(embedding.cpu().numpy())
            valid_titles.append(title)
        else:
            failed_titles.append(title)
            logger.warning(f"Failed to get embedding for title {i}: {title[:50]}...")
    
    logger.info(f"Embedding computation completed")
    
    if len(embeddings) < 2:
        logger.error("Need at least 2 valid embeddings for visualization")
        return False
    
    logger.info(f"Successfully computed {len(embeddings)} embeddings out of {len(titles)} titles")
    if failed_titles:
        logger.info(f"Failed to get embeddings for {len(failed_titles)} titles")
    
    # Convert to numpy array
    embeddings_array = np.array(embeddings)
    logger.info(f"Embedding shape: {embeddings_array.shape}")
    
    logger.info("Creating matplotlib figure...")
    # Create visualization
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))
    logger.info("Matplotlib figure created successfully")
    
    # Method 1: PCA to 2D
    logger.info("Computing PCA reduction...")
    pca = PCA(n_components=2)
    embeddings_2d_pca = pca.fit_transform(embeddings_array)
    logger.info("PCA reduction completed")
    
    # Method 2: t-SNE to 2D
    logger.info("Computing t-SNE reduction...")
    tsne = TSNE(n_components=2, random_state=42, perplexity=min(30, len(embeddings)-1))
    embeddings_2d_tsne = tsne.fit_transform(embeddings_array)
    logger.info("t-SNE reduction completed")
    
    # Use a neutral color scheme based on position in the dataset
    colors = plt.cm.plasma(np.linspace(0, 1, len(embeddings)))
    
    # Plot PCA
    scatter1 = ax1.scatter(embeddings_2d_pca[:, 0], embeddings_2d_pca[:, 1], 
                           c=colors, alpha=0.7, s=50)
    ax1.set_title(f'PCA Visualization of {len(embeddings)} Headlines\n(Explained variance: {pca.explained_variance_ratio_.sum():.2%})', 
                  fontsize=14, fontweight='bold')
    ax1.set_xlabel('Principal Component 1')
    ax1.set_ylabel('Principal Component 2')
    ax1.grid(True, alpha=0.3)
    
    # Plot t-SNE
    scatter2 = ax2.scatter(embeddings_2d_tsne[:, 0], embeddings_2d_tsne[:, 1], 
                           c=colors, alpha=0.7, s=50)
    ax2.set_title(f't-SNE Visualization of {len(embeddings)} Headlines', 
                  fontsize=14, fontweight='bold')
    ax2.set_xlabel('t-SNE Component 1')
    ax2.set_ylabel('t-SNE Component 2')
    ax2.grid(True, alpha=0.3)
    
    # Add colorbar
    cbar = plt.colorbar(scatter1, ax=[ax1, ax2], shrink=0.8)
    cbar.set_label('Dataset Position', rotation=270, labelpad=20)
    
    # Add some statistics
    mode_display = mode if mode else "All modes (local cache)"
    stats_text = f"""
Statistics:
• Total headlines: {len(embeddings)}
• Original dimensions: {embeddings_array.shape[1]}
• PCA explained variance: {pca.explained_variance_ratio_.sum():.2%}
• Dataset size: {len(previous_selections)} selections
• Source: {mode_display}
    """
    
    plt.figtext(0.02, 0.02, stats_text, fontsize=10, 
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.8))
    
    # Add title
    title_mode = mode.upper() if mode else "ALL MODES"
    plt.suptitle(f'Headline Embedding Visualization - {title_mode}', 
                 fontsize=16, fontweight='bold', y=0.95)
    
    # Adjust layout and save
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    logger.info(f"Visualization saved to: {output_file}")
    
    # Also create a 3D version if we have enough data
    if len(embeddings) >= 10:
        logger.info("Creating 3D visualization...")
        fig_3d = plt.figure(figsize=(15, 10))
        ax_3d = fig_3d.add_subplot(111, projection='3d')
        
        # Use PCA for 3D
        pca_3d = PCA(n_components=3)
        embeddings_3d = pca_3d.fit_transform(embeddings_array)
        
        scatter_3d = ax_3d.scatter(embeddings_3d[:, 0], embeddings_3d[:, 1], embeddings_3d[:, 2],
                                   c=colors, alpha=0.7, s=50)
        ax_3d.set_title(f'3D PCA Visualization of {len(embeddings)} Headlines\n(Explained variance: {pca_3d.explained_variance_ratio_.sum():.2%})',
                        fontsize=14, fontweight='bold')
        ax_3d.set_xlabel('Principal Component 1')
        ax_3d.set_ylabel('Principal Component 2')
        ax_3d.set_zlabel('Principal Component 3')
        
        # Add colorbar
        cbar_3d = plt.colorbar(scatter_3d, ax=ax_3d, shrink=0.8)
        cbar_3d.set_label('Dataset Position', rotation=270, labelpad=20)
        
        # Save 3D version
        output_file_3d = output_file.replace('.png', '_3d.png')
        plt.savefig(output_file_3d, dpi=300, bbox_inches='tight')
        logger.info(f"3D visualization saved to: {output_file_3d}")
        plt.close(fig_3d)
    
    plt.close(fig)
    return True


def run_visualization_mode(mode=None):
    """Run the visualization mode to create embedding plots."""
    logger.info("--- Running Visualization Mode ---")
    
    # Create visualization (mode is optional now)
    success = create_embedding_visualization(mode)
    
    if success:
        logger.info("Visualization mode completed successfully")
        return 0
    else:
        logger.error("Visualization mode failed")
        return 1


if __name__ == "__main__":
    """Run the visualization script independently."""
    parser = argparse.ArgumentParser(description='Create embedding visualization')
    parser.add_argument('--mode', type=str, help='Mode name for cache key (optional)')
    parser.add_argument('--output', type=str, default='embedding_visualization.png', 
                       help='Output filename for visualization')
    
    args = parser.parse_args()
    
    # Use the configured log level (same pattern as auto_update.py)
    logger.info(f"Visualization starting with log level: {LOG_LEVEL}")
    
    logger.info("Starting standalone visualization script")
    
    # Create visualization
    success = create_embedding_visualization(args.mode, args.output)
    
    if success:
        logger.info("Visualization completed successfully")
        sys.exit(0)
    else:
        logger.error("Visualization failed")
        sys.exit(1)
