import React from 'react';
import type { InputHTMLAttributes } from 'react';
import './Input.css';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: string;
}

export const Input: React.FC<InputProps> = ({ className = '', error, ...props }) => {
  return (
    <div className="input-wrapper">
      <input 
        className={`input ${error ? 'input-error' : ''} ${className}`} 
        {...props} 
      />
      {error && <span className="input-error-msg">{error}</span>}
    </div>
  );
};
