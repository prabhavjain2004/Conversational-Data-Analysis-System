"use client";

import { useEffect, useRef } from "react";

interface PlotlyRendererProps {
  figure: {
    data: any[];
    layout: any;
  };
  chartId: string;
}

export default function PlotlyRenderer({ figure, chartId }: PlotlyRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;

    const loadAndRender = async () => {
      // Check if Plotly is already available globally
      if (typeof window !== "undefined" && !(window as any).Plotly) {
        await new Promise<void>((resolve, reject) => {
          const script = document.createElement("script");
          script.src = "https://cdn.plot.ly/plotly-2.35.0.min.js";
          script.async = true;
          script.onload = () => resolve();
          script.onerror = () => reject(new Error("Failed to load Plotly CDN"));
          document.head.appendChild(script);
        });
      }

      if (!active || !containerRef.current) return;

      const Plotly = (window as any).Plotly;
      if (Plotly) {
        // Enforce dark mode aesthetics on LLM-generated layout
        const layoutCopy = {
          ...figure.layout,
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          font: {
            family: "Plus Jakarta Sans, sans-serif",
            color: "#f3f4f6",
          },
          margin: { t: 40, r: 20, l: 40, b: 40 },
          autosize: true,
        };

        if (layoutCopy.xaxis) {
          layoutCopy.xaxis.gridcolor = "rgba(255,255,255,0.06)";
          layoutCopy.xaxis.zerolinecolor = "rgba(255,255,255,0.1)";
        }
        if (layoutCopy.yaxis) {
          layoutCopy.yaxis.gridcolor = "rgba(255,255,255,0.06)";
          layoutCopy.yaxis.zerolinecolor = "rgba(255,255,255,0.1)";
        }

        Plotly.newPlot(containerRef.current, figure.data, layoutCopy, {
          responsive: true,
          displayModeBar: false,
        });
      }
    };

    loadAndRender().catch((err) => console.error("Error rendering chart:", err));

    // Handle Window Resizing
    const handleResize = () => {
      const Plotly = (window as any).Plotly;
      if (Plotly && containerRef.current) {
        Plotly.Plots.resize(containerRef.current);
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      active = false;
      window.removeEventListener("resize", handleResize);
    };
  }, [figure, chartId]);

  return (
    <div className="w-full relative overflow-hidden" style={{ minHeight: "350px" }}>
      <div 
        ref={containerRef} 
        id={chartId} 
        className="w-full h-full min-h-[350px]"
      />
    </div>
  );
}
