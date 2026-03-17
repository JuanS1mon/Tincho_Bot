import { useState, useRef, useEffect } from 'react';

export interface FloatPosition {
  x: number;
  y: number;
}

export interface FloatViewport {
  width: number;
  height: number;
}

type FloatDefaultPos = FloatPosition | ((viewport: FloatViewport) => FloatPosition);

const DEFAULT_POS: FloatPosition = { x: 0, y: 0 };

export function useDraggableFloat<T extends HTMLElement = HTMLDivElement>(storageKey: string, defaultPos: FloatDefaultPos = DEFAULT_POS) {
  const initialPos = typeof defaultPos === 'function' ? DEFAULT_POS : defaultPos;
  const [position, setPosition] = useState<FloatPosition>(initialPos);
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState<FloatPosition>({ x: 0, y: 0 });
  const elementRef = useRef<T>(null);
  const [isLoaded, setIsLoaded] = useState(false);

  // Load position from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem(storageKey);
    if (stored) {
      try {
        setPosition(JSON.parse(stored));
      } catch (e) {
        console.warn('Failed to load float position', e);
      }
    } else if (typeof defaultPos === 'function') {
      const resolved = defaultPos({
        width: window.innerWidth,
        height: window.innerHeight,
      });
      setPosition(resolved);
    }
    setIsLoaded(true);
  }, [storageKey]);

  // Save position to localStorage whenever it changes
  useEffect(() => {
    if (!isLoaded) return;
    localStorage.setItem(storageKey, JSON.stringify(position));
  }, [position, storageKey, isLoaded]);

  const snapToEdge = (x: number, y: number, width: number, height: number) => {
    const windowWidth = window.innerWidth;
    const windowHeight = window.innerHeight;
    const snappingThreshold = 40; // Distance from edge to trigger snap

    let snappedX = x;
    let snappedY = y;

    // Snap horizontally (left or right edge)
    if (x < snappingThreshold) {
      snappedX = 0;
    } else if (x + width > windowWidth - snappingThreshold) {
      snappedX = windowWidth - width;
    }

    // Snap vertically (top or bottom edge)
    if (y < snappingThreshold) {
      snappedY = 0;
    } else if (y + height > windowHeight - snappingThreshold) {
      snappedY = windowHeight - height;
    }

    // Clamp to visible boundaries
    snappedX = Math.max(0, Math.min(snappedX, windowWidth - width));
    snappedY = Math.max(0, Math.min(snappedY, windowHeight - height));

    return { x: snappedX, y: snappedY };
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLElement>) => {
    if (!elementRef.current) return;

    const rect = elementRef.current.getBoundingClientRect();
    setDragOffset({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
    setIsDragging(true);
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging || !elementRef.current) return;

    const newX = e.clientX - dragOffset.x;
    const newY = e.clientY - dragOffset.y;

    const { width, height } = elementRef.current.getBoundingClientRect();
    
    // Clamp to visible boundaries while dragging (soft)
    const clampedX = Math.max(0, Math.min(newX, window.innerWidth - width));
    const clampedY = Math.max(0, Math.min(newY, window.innerHeight - height));

    setPosition({ x: clampedX, y: clampedY });
  };

  const handleMouseUp = () => {
    if (isDragging && elementRef.current) {
      const rect = elementRef.current.getBoundingClientRect();
      const snapped = snapToEdge(rect.left, rect.top, rect.width, rect.height);
      setPosition(snapped);
    }
    setIsDragging(false);
  };

  // Add event listeners
  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, dragOffset]);

  return {
    position,
    isDragging,
    elementRef,
    handleMouseDown,
    style: {
      position: 'fixed' as const,
      left: `${position.x}px`,
      top: `${position.y}px`,
      cursor: isDragging ? 'grabbing' : 'grab',
      transition: isDragging ? 'none' : 'all 0.2s ease-out',
      zIndex: 40,
    } as React.CSSProperties,
  };
}
