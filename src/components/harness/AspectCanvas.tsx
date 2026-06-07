import type { HTMLAttributes, ReactNode } from "react";

type AspectCanvasProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  variant?: "immersive" | "surface";
};

export function AspectCanvas({
  children,
  className = "",
  variant = "immersive",
  ...props
}: AspectCanvasProps) {
  return (
    <div className={`aspect-canvas aspect-canvas--${variant} ${className}`} {...props}>
      {children}
    </div>
  );
}
