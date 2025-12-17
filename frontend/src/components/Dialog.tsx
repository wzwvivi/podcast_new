import React from 'react';
import { XIcon } from './Icons';

interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm?: () => void;
  onCancel?: () => void;
  type?: 'confirm' | 'alert';
}

const Dialog: React.FC<DialogProps> = ({
  isOpen,
  onClose,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  onConfirm,
  onCancel,
  type = 'confirm'
}) => {
  if (!isOpen) return null;

  const handleConfirm = () => {
    if (onConfirm) {
      onConfirm();
    }
    onClose();
  };

  const handleCancel = () => {
    if (onCancel) {
      onCancel();
    }
    onClose();
  };

  return (
    <>
      {/* Overlay */}
      <div 
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 animate-in fade-in duration-200"
        onClick={handleCancel}
      />
      
      {/* Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div 
          className="bg-dark-card border border-dark-border rounded-xl shadow-2xl max-w-md w-full p-6 animate-in fade-in slide-in-from-bottom-4 duration-300"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between mb-4">
            <h3 className="text-lg font-semibold text-white">{title}</h3>
            <button
              onClick={handleCancel}
              className="text-gray-400 hover:text-white transition-colors p-1 rounded-md hover:bg-zinc-800"
            >
              <XIcon className="w-5 h-5" />
            </button>
          </div>
          
          {/* Message */}
          <div className="mb-6">
            <p className="text-gray-300 whitespace-pre-wrap leading-relaxed">{message}</p>
          </div>
          
          {/* Actions */}
          <div className="flex gap-3 justify-end">
            {type === 'confirm' && (
              <button
                onClick={handleCancel}
                className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-gray-300 rounded-lg transition-colors text-sm font-medium"
              >
                {cancelText}
              </button>
            )}
            <button
              onClick={handleConfirm}
              className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white rounded-lg transition-colors text-sm font-medium shadow-lg shadow-brand-500/20"
            >
              {confirmText}
            </button>
          </div>
        </div>
      </div>
    </>
  );
};

export default Dialog;

