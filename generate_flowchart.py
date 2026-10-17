# generate_flowchart.py
"""Generates a Mermaid flowchart string and saves it for Draw.io import."""

mermaid_code = """
graph TD
    %% Node Styling
    classDef runner fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef itemClass fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef manifestClass fill:#e8f5e9,stroke:#388e3c,stroke-width:2px;
    classDef output fill:#fff3e0,stroke:#f57c00,stroke-width:2px;

    subgraph Data_Ingestion [Data Ingestion Layer]
        A[Raw CSV Manifest / Web Scraper]
    end

    subgraph Core_Runner [inventory_analyzer4.py - Execution Pipe]
        B[main function]
        C{Try Row Parsing}
        D[Skip Row & Print Error]
        E[Instantiate LotItem]
        F[batch.add_item item]
        G[batch.get_profitable_items MIN_MARGIN]
        H[Sort Winners Descending by Margin]
    end

    subgraph Unit_Worker [lot_item.py - LotItem Blueprint]
        I[LotItem Class]
        I1[self.bid / self.premium / self.tax / self.sale_price]
        I2[calculate_true_cost]
        I3[calculate_net_profit]
        I4[calculate_margin]
        I5[calculate_max_bid target_margin]
    end

    subgraph Container_Manager [manifest.py - Manifest Class]
        J[Manifest Class]
        J1[self.items = list of LotItems]
        J2[add_item]
        J3[total_required_capital]
        J4[total_projected_profit]
        J5[get_profitable_items]
    end

    subgraph Data_Output [Output Layer]
        K[profitable_lots.csv]
        L[Terminal Batch Summary Printout]
    end

    %% Pipeline Connections
    A -->|Reads Raw Row Dicts| B
    B --> C
    C -->|ValueError| D
    C -->|Valid Numeric Data| E
    E -->|1. Creates Object| I
    E -->|2. Hands Object To| F
    F -->|Appends to self.items| J
    J --> J2
    J2 --> J1
    
    B --> G
    G -->|Queries Margin via| J5
    J5 -->|Evaluates calculate_margin| I4
    G -->|Returns Surviving Objects| H
    
    H -->|Generates Row Dicts| K
    H -->|Queries Capital & Profit| L
    L -.->|Calls| J3
    L -.->|Calls| J4

    %% Apply Classes
    class B,C,D,E,F,G,H runner;
    class I,I1,I2,I3,I4,I5 itemClass;
    class J,J1,J2,J3,J4,J5 manifestClass;
    class K,L output;
"""


def main():
    output_filename = "architecture_flowchart.mmd"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(mermaid_code.strip())

    print(
        f"Flowchart successfully generated and saved to '{output_filename}'!"
    )
    print("\n" + "=" * 50)
    print("COPY THE MERMAID CODE BELOW FOR DIRECT DRAW.IO IMPORT:")
    print("=" * 50 + "\n")
    print(mermaid_code.strip())


if __name__ == "__main__":
    main()