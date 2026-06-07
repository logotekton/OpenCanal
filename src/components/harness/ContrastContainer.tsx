import type { CSSProperties, HTMLAttributes, ReactNode } from "react";
import { useEffect, useState } from "react";

type ContrastContainerProps = HTMLAttributes<HTMLDivElement> & {
  imageUrl?: string;
  bgImage?: string;
  fallbackColor?: string;
  children: ReactNode;
};

export function ContrastContainer({
  imageUrl,
  bgImage,
  fallbackColor = "#061018",
  children,
  className = "",
  style,
  ...props
}: ContrastContainerProps) {
  const activeImage = imageUrl ?? bgImage ?? "";
  const [lowKey, setLowKey] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!activeImage) {
      setFailed(true);
      setLowKey(true);
      return;
    }

    const image = new Image();
    image.crossOrigin = "anonymous";
    image.src = activeImage;
    image.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d");
        if (!context) return;

        canvas.width = 10;
        canvas.height = 10;
        context.drawImage(image, 0, 0, 10, 10);
        const pixels = context.getImageData(0, 0, 10, 10).data;
        let total = 0;

        for (let index = 0; index < pixels.length; index += 4) {
          total += pixels[index] * 0.299 + pixels[index + 1] * 0.587 + pixels[index + 2] * 0.114;
        }

        setLowKey(total / (pixels.length / 4) < 128);
        setFailed(false);
      } catch {
        setLowKey(true);
        setFailed(false);
      }
    };
    image.onerror = () => {
      setFailed(true);
      setLowKey(true);
    };
  }, [activeImage]);

  const containerStyle: CSSProperties = {
    ...style,
    backgroundColor: failed || !activeImage ? fallbackColor : undefined,
    backgroundImage: failed || !activeImage ? undefined : `url(${activeImage})`
  };

  return (
    <div
      className={`contrast-container ${lowKey ? "contrast-container--low" : "contrast-container--high"} ${className}`}
      style={containerStyle}
      {...props}
    >
      <div className="contrast-container__veil" />
      <div className="contrast-container__content">{children}</div>
    </div>
  );
}
