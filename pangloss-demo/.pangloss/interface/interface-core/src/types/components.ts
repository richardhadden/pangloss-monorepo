/**
 * The props of the components of the library, and the map of them that can be
 * overridden. This is the bottom layer: it imports nothing else of the library, so
 * that anything can use these types without a circular dependency.
 */
import type { JSX } from "@solidjs/web";
import type { Component } from "solid-js";

export interface ButtonProps {
  type?: "button" | "submit";
  disabled?: boolean;
  onClick?: (event: MouseEvent) => void;
  children?: JSX.Element;
}

export interface ErrorMessageProps {
  error: unknown;
}

export interface EntityCardProps {
  id: string;
  type: string;
  label: string;
}

export interface FieldListProps {
  /** The name of a model */
  model: string;
}

/**
 * Every component that an application can replace. A component of the library gets
 * the others it uses with `useComponent`, never by importing them, so that an
 * override is used everywhere.
 */
export interface ComponentMap {
  Button: Component<ButtonProps>;
  ErrorMessage: Component<ErrorMessageProps>;
  EntityCard: Component<EntityCardProps>;
  FieldList: Component<FieldListProps>;
}

export type ComponentName = keyof ComponentMap;
