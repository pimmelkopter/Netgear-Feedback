import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

const VlanManager = () => {
  const [portVlans, setPortVlans] = useState({});
  const [vlanColors, setVlanColors] = useState({});
  const [vlanNames, setVlanNames] = useState({});
  const [selectedVlan, setSelectedVlan] = useState(null);
  const [pendingChanges, setPendingChanges] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch initial data
  useEffect(() => {
    fetchData();
    // Set up periodic refresh
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      const response = await fetch('/api/refresh', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) throw new Error('Network response was not ok');
      
      const data = await response.json();
      if (data.status === 'success') {
        setPortVlans(data.port_vlans);
        setVlanColors(data.vlan_colors);
        setVlanNames(data.vlan_names);
      } else {
        throw new Error(data.message || 'Failed to fetch data');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleVlanSelect = (vlanId) => {
    setSelectedVlan(selectedVlan === vlanId ? null : vlanId);
  };

  const handlePortClick = (portId) => {
    if (!selectedVlan) return;

    setPendingChanges(prev => {
      const newChanges = { ...prev };
      if (newChanges[portId] === selectedVlan) {
        delete newChanges[portId];
      } else {
        newChanges[portId] = selectedVlan;
      }
      return newChanges;
    });
  };

  const applyChanges = async () => {
    setIsLoading(true);
    try {
      // Apply each change sequentially
      for (const [portId, vlanId] of Object.entries(pendingChanges)) {
        const response = await fetch(`/api/switch/port/${portId}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ vlan: vlanId })
        });
        
        if (!response.ok) {
          throw new Error(`Failed to update port ${portId}`);
        }
      }
      
      // Refresh data after changes
      await fetchData();
      setPendingChanges({});
      setSelectedVlan(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const cancelChanges = () => {
    setPendingChanges({});
    setSelectedVlan(null);
  };

  const getPortColor = (portId) => {
    const vlanId = pendingChanges[portId] || portVlans[portId];
    return vlanColors[vlanId] || 'rgb(128, 128, 128)';
  };

  const buttonStyles = (isSelected) => `
    p-4 rounded-lg transition-all duration-200
    ${isSelected ? 'ring-2 ring-red-500 ring-offset-2' : ''}
    hover:shadow-lg
  `;

  if (isLoading && Object.keys(portVlans).length === 0) {
    return <div className="p-8 text-center">Loading...</div>;
  }

  if (error) {
    return (
      <div className="p-8 text-center text-red-600">
        Error: {error}
        <button 
          onClick={fetchData}
          className="ml-4 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8 p-4">
      {/* Port Grid */}
      <Card>
        <CardHeader>
          <CardTitle>Ports</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Odd Ports Row */}
            <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-12 gap-2">
              {Object.entries(portVlans)
                .filter(([portId]) => parseInt(portId) % 2 === 1)
                .map(([portId]) => (
                  <button
                    key={portId}
                    className={`${buttonStyles(portId in pendingChanges)} min-h-20`}
                    style={{
                      backgroundColor: getPortColor(parseInt(portId)),
                      color: 'white',
                      textShadow: '1px 1px 1px rgba(0,0,0,0.5)'
                    }}
                    onClick={() => handlePortClick(parseInt(portId))}
                    disabled={isLoading}
                  >
                    <div className="font-bold">Port {portId}</div>
                    <div className="text-sm">
                      {vlanNames[pendingChanges[portId] || portVlans[portId]] || 
                       `VLAN ${pendingChanges[portId] || portVlans[portId]}`}
                    </div>
                  </button>
              ))}
            </div>
            
            {/* Even Ports Row */}
            <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-12 gap-2">
              {Object.entries(portVlans)
                .filter(([portId]) => parseInt(portId) % 2 === 0)
                .map(([portId]) => (
                  <button
                    key={portId}
                    className={`${buttonStyles(portId in pendingChanges)} min-h-20`}
                    style={{
                      backgroundColor: getPortColor(parseInt(portId)),
                      color: 'white',
                      textShadow: '1px 1px 1px rgba(0,0,0,0.5)'
                    }}
                    onClick={() => handlePortClick(parseInt(portId))}
                    disabled={isLoading}
                  >
                    <div className="font-bold">Port {portId}</div>
                    <div className="text-sm">
                      {vlanNames[pendingChanges[portId] || portVlans[portId]] || 
                       `VLAN ${pendingChanges[portId] || portVlans[portId]}`}
                    </div>
                  </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* VLAN Selection */}
      <Card>
        <CardHeader>
          <CardTitle>VLANs</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {Object.entries(vlanColors).map(([vlanId, color]) => (
              <button
                key={vlanId}
                className={buttonStyles(selectedVlan === parseInt(vlanId))}
                style={{
                  backgroundColor: color,
                  color: 'white',
                  textShadow: '1px 1px 1px rgba(0,0,0,0.5)'
                }}
                onClick={() => handleVlanSelect(parseInt(vlanId))}
                disabled={isLoading}
              >
                <div className="font-bold">
                  {vlanNames[vlanId] || `VLAN ${vlanId}`}
                </div>
                <div className="text-sm">
                  {Object.values(portVlans).filter(v => v === parseInt(vlanId)).length} Ports
                </div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Action Buttons */}
      <div className="flex justify-end space-x-4">
        <button
          className={`px-4 py-2 rounded-lg ${
            Object.keys(pendingChanges).length === 0
              ? 'bg-gray-300 cursor-not-allowed'
              : 'bg-gray-500 hover:bg-gray-600 text-white'
          }`}
          onClick={cancelChanges}
          disabled={Object.keys(pendingChanges).length === 0 || isLoading}
        >
          Cancel Changes
        </button>
        <button
          className={`px-4 py-2 rounded-lg ${
            Object.keys(pendingChanges).length === 0
              ? 'bg-gray-300 cursor-not-allowed'
              : 'bg-green-500 hover:bg-green-600 text-white'
          }`}
          onClick={applyChanges}
          disabled={Object.keys(pendingChanges).length === 0 || isLoading}
        >
          Apply Changes
        </button>
      </div>
    </div>
  );
};

export default VlanManager;