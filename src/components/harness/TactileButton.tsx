import type { ButtonHTMLAttributes, ReactNode } from "react";

type TactileButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  tone?: "primary" | "quiet" | "glass";
};

export function TactileButton({
  children,
  className = "",
  tone = "primary",
  type = "button",
  ...props
}: TactileButtonProps) {
  return (
    <button className={`tactile-button tactile-button--${tone} ${className}`} type={type} {...props}>
      {children}
    </button>
  );
}
