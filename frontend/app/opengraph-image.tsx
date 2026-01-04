import { ImageResponse } from 'next/og';

export const runtime = 'edge';
export const alt = 'InterviewLab - AI-Powered Interview Preparation';
export const size = {
  width: 1200,
  height: 630,
};
export const contentType = 'image/png';

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-start',
          justifyContent: 'center',
          padding: '80px',
          position: 'relative',
        }}
      >
        {/* Decorative circles */}
        <div
          style={{
            position: 'absolute',
            top: '50px',
            left: '100px',
            width: '200px',
            height: '200px',
            borderRadius: '50%',
            background: 'rgba(255, 255, 255, 0.1)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            bottom: '50px',
            right: '100px',
            width: '300px',
            height: '300px',
            borderRadius: '50%',
            background: 'rgba(255, 255, 255, 0.1)',
          }}
        />
        
        {/* Icon */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '40px',
            marginBottom: '40px',
          }}
        >
          <div
            style={{
              width: '120px',
              height: '120px',
              borderRadius: '24px',
              background: 'rgba(255, 255, 255, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '60px',
            }}
          >
            💼
          </div>
          
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <h1
              style={{
                fontSize: '72px',
                fontWeight: 'bold',
                color: 'white',
                margin: 0,
                lineHeight: '1.2',
              }}
            >
              InterviewLab
            </h1>
            <p
              style={{
                fontSize: '36px',
                color: 'rgba(255, 255, 255, 0.9)',
                margin: '10px 0 0 0',
              }}
            >
              AI-Powered Interview Preparation
            </p>
          </div>
        </div>
        
        {/* Features */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '20px',
            marginTop: '40px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <div
              style={{
                width: '12px',
                height: '12px',
                borderRadius: '50%',
                background: 'white',
              }}
            />
            <span style={{ fontSize: '28px', color: 'rgba(255, 255, 255, 0.9)' }}>
              Voice Practice Sessions
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <div
              style={{
                width: '12px',
                height: '12px',
                borderRadius: '50%',
                background: 'white',
              }}
            />
            <span style={{ fontSize: '28px', color: 'rgba(255, 255, 255, 0.9)' }}>
              Resume Analysis
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <div
              style={{
                width: '12px',
                height: '12px',
                borderRadius: '50%',
                background: 'white',
              }}
            />
            <span style={{ fontSize: '28px', color: 'rgba(255, 255, 255, 0.9)' }}>
              Live Code Practice
            </span>
          </div>
        </div>
      </div>
    ),
    {
      ...size,
    }
  );
}


